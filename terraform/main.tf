locals {
  domain         = "${var.duckdns_subdomain}.duckdns.org"
  grafana_url    = "http://${aws_eip.monitoring.public_ip}:3000"
  app_health_url = "http://${var.app_server_metrics_host}:${var.app_server_app_port}/api/v1/health"
}

# ── Account ID (used to scope IAM policy to this account's SSM parameters) ────
data "aws_caller_identity" "current" {}

# ── SSM Parameter Store: secrets the bootstrap script fetches at runtime ───────
# SecureString parameters are encrypted with the AWS-managed SSM KMS key.
# Values are stored here rather than in Terraform state plaintext or SSH env vars.
resource "aws_ssm_parameter" "slack_webhook_url" {
  name  = "/lgtm/slack_webhook_url"
  type  = "SecureString"
  value = var.slack_webhook_url
}

resource "aws_ssm_parameter" "slack_channel" {
  name  = "/lgtm/slack_channel"
  type  = "String"
  value = var.slack_channel
}

resource "aws_ssm_parameter" "alert_email_recipients" {
  name  = "/lgtm/alert_email_recipients"
  type  = "SecureString"
  value = join(",", var.alert_email_recipients)
}

resource "aws_ssm_parameter" "smtp_smarthost" {
  name  = "/lgtm/smtp_smarthost"
  type  = "String"
  value = var.smtp_smarthost
}

resource "aws_ssm_parameter" "smtp_from" {
  name  = "/lgtm/smtp_from"
  type  = "String"
  value = var.smtp_from
}

resource "aws_ssm_parameter" "smtp_auth_username" {
  name  = "/lgtm/smtp_auth_username"
  type  = "SecureString"
  value = var.smtp_auth_username
}

resource "aws_ssm_parameter" "smtp_auth_password" {
  name  = "/lgtm/smtp_auth_password"
  type  = "SecureString"
  value = var.smtp_auth_password
}

resource "aws_ssm_parameter" "smtp_require_tls" {
  name  = "/lgtm/smtp_require_tls"
  type  = "String"
  value = tostring(var.smtp_require_tls)
}

resource "aws_ssm_parameter" "grafana_admin_password" {
  name  = "/lgtm/grafana_admin_password"
  type  = "SecureString"
  value = var.grafana_admin_password
}

resource "aws_ssm_parameter" "duckdns_token" {
  name  = "/lgtm/duckdns_token"
  type  = "SecureString"
  value = var.duckdns_token
}

resource "aws_ssm_parameter" "duckdns_subdomain" {
  name  = "/lgtm/duckdns_subdomain"
  type  = "String"
  value = var.duckdns_subdomain
}

resource "aws_ssm_parameter" "app_server_metrics_host" {
  name  = "/lgtm/app_server_metrics_host"
  type  = "String"
  value = var.app_server_metrics_host
}

resource "aws_ssm_parameter" "app_server_source_cidr" {
  name  = "/lgtm/app_server_source_cidr"
  type  = "String"
  value = var.app_server_source_cidr
}

resource "aws_ssm_parameter" "app_server_app_port" {
  name  = "/lgtm/app_server_app_port"
  type  = "String"
  value = tostring(var.app_server_app_port)
}

resource "aws_ssm_parameter" "app_server_node_exporter_port" {
  name  = "/lgtm/app_server_node_exporter_port"
  type  = "String"
  value = tostring(var.app_server_node_exporter_port)
}

resource "aws_ssm_parameter" "app_server_health_url" {
  name  = "/lgtm/app_server_health_url"
  type  = "String"
  value = local.app_health_url
}

# ── IAM role: lets the EC2 instance read /lgtm/* SSM parameters ───────────────
resource "aws_iam_role" "monitoring" {
  name = "lgtm-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "monitoring_ssm" {
  name = "lgtm-monitoring-ssm-read"
  role = aws_iam_role.monitoring.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/lgtm/*"
      },
      {
        # Allow KMS decrypt only when called via SSM (scoped to the managed SSM key)
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com" } }
      }
    ]
  })
}

resource "aws_iam_instance_profile" "monitoring" {
  name = "lgtm-monitoring-profile"
  role = aws_iam_role.monitoring.name
}

# ── AMI: latest Ubuntu 22.04 LTS (Canonical) ──────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── VPC and public subnet ──────────────────────────────────────────────────────
resource "aws_vpc" "monitoring" {
  cidr_block           = "10.100.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "lgtm-monitoring-vpc" }
}

resource "aws_subnet" "monitoring_public" {
  vpc_id                  = aws_vpc.monitoring.id
  cidr_block              = "10.100.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = false

  tags = { Name = "lgtm-monitoring-public" }
}

resource "aws_internet_gateway" "monitoring" {
  vpc_id = aws_vpc.monitoring.id

  tags = { Name = "lgtm-monitoring-igw" }
}

resource "aws_route_table" "monitoring_public" {
  vpc_id = aws_vpc.monitoring.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.monitoring.id
  }

  tags = { Name = "lgtm-monitoring-rt" }
}

resource "aws_route_table_association" "monitoring_public" {
  subnet_id      = aws_subnet.monitoring_public.id
  route_table_id = aws_route_table.monitoring_public.id
}

# ── Security group ─────────────────────────────────────────────────────────────
# Inbound default-deny: SSH is restricted to engineers, public monitoring UI
# ports are controlled by var.public_monitoring_cidrs. Outbound unrestricted so
# Prometheus can scrape app-server node-exporter and Blackbox can probe app
# endpoints.
resource "aws_security_group" "monitoring" {
  name        = "lgtm-monitoring-sg"
  description = "LGTM monitoring - engineer access + app server telemetry only"
  vpc_id      = aws_vpc.monitoring.id

  ingress {
    description = "SSH from engineers"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.engineer_ips
  }

  ingress {
    description = "HTTP for monitoring domain"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.public_monitoring_cidrs
  }

  ingress {
    description = "HTTPS for monitoring domain"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.public_monitoring_cidrs
  }

  ingress {
    description = "Grafana public UI"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.public_monitoring_cidrs
  }

  ingress {
    description = "Prometheus UI public"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = var.public_monitoring_cidrs
  }

  ingress {
    description = "Alertmanager UI public"
    from_port   = 9093
    to_port     = 9093
    protocol    = "tcp"
    cidr_blocks = var.public_monitoring_cidrs
  }

  # Pushgateway is open to 0.0.0.0/0 so GitHub Actions can push DORA metrics
  # directly from the runner without needing SSH. Pushgateway has no built-in
  # auth — access relies on the IP being non-guessable (Elastic IP, not public
  # DNS). For higher security, add a reverse proxy with bearer token auth.
  ingress {
    description = "Pushgateway is open for GitHub Actions DORA metric pushes"
    from_port   = 9091
    to_port     = 9091
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Cross-server ingress rules (OTLP, Loki) are added via aws_security_group_rule
  # resources below for the existing app server CIDR.

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "lgtm-monitoring-sg" }
}

# ── Key pair: import your local public key into AWS ────────────────────────────
resource "aws_key_pair" "monitoring" {
  key_name   = "lgtm-monitoring-key"
  public_key = file(var.ssh_public_key_path)

  tags = { Name = "lgtm-monitoring-key" }
}

# ── EC2 instance ───────────────────────────────────────────────────────────────
resource "aws_instance" "monitoring" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.monitoring.key_name
  subnet_id              = aws_subnet.monitoring_public.id
  vpc_security_group_ids = [aws_security_group.monitoring.id]
  iam_instance_profile   = aws_iam_instance_profile.monitoring.name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 40 # Prometheus TSDB + Loki chunks + Tempo trace blocks
    delete_on_termination = true
  }

  tags = { Name = "lgtm-monitoring" }
}

# ── Elastic IP ─────────────────────────────────────────────────────────────────
resource "aws_eip" "monitoring" {
  domain = "vpc"
  tags   = { Name = "lgtm-monitoring-eip" }
}

resource "aws_eip_association" "monitoring" {
  instance_id   = aws_instance.monitoring.id
  allocation_id = aws_eip.monitoring.id
}

# ── Bootstrap: upload and run lgtm-stack.sh ───────────────────────────────────
# Secrets are written to a 600-permissions env file uploaded via the encrypted
# SSH session, sourced into the script, then immediately deleted. Values are
# still stored in Terraform state — use an encrypted S3 backend with restricted
# access policies to protect them at rest.
resource "null_resource" "bootstrap" {
  triggers = {
    instance_id = aws_instance.monitoring.id
  }

  depends_on = [
    aws_eip_association.monitoring,
    aws_ssm_parameter.alert_email_recipients,
    aws_ssm_parameter.app_server_app_port,
    aws_ssm_parameter.app_server_health_url,
    aws_ssm_parameter.app_server_metrics_host,
    aws_ssm_parameter.app_server_node_exporter_port,
    aws_ssm_parameter.app_server_source_cidr,
    aws_ssm_parameter.monitoring_server_ip,
    aws_ssm_parameter.smtp_auth_password,
    aws_ssm_parameter.smtp_auth_username,
    aws_ssm_parameter.smtp_from,
    aws_ssm_parameter.smtp_require_tls,
    aws_ssm_parameter.smtp_smarthost,
  ]

  connection {
    type        = "ssh"
    user        = "ubuntu"
    private_key = file(var.ssh_private_key_path)
    host        = aws_eip.monitoring.public_ip
    timeout     = "10m"
  }

  # Wait for cloud-init to finish initialising the instance before anything else
  provisioner "remote-exec" {
    inline = ["cloud-init status --wait || true"]
  }

  provisioner "remote-exec" {
    inline = ["mkdir -p /tmp/lgtm-dashboards"]
  }

  provisioner "file" {
    source      = "../dashboards/"
    destination = "/tmp/lgtm-dashboards"
  }

  provisioner "file" {
    source      = "../scripts/lgtm-stack.sh"
    destination = "/tmp/lgtm-stack.sh"
  }

  # The script fetches SLACK_WEBHOOK_URL and GRAFANA_PASSWORD directly from
  # SSM using the instance's IAM role — no secrets flow through SSH.
  provisioner "remote-exec" {
    inline = [
      "chmod +x /tmp/lgtm-stack.sh",
      "sudo bash /tmp/lgtm-stack.sh",
      "rm -f /tmp/lgtm-stack.sh"
    ]
  }
}

# ── SSM: store monitoring server IPs so bootstrap scripts can find it ─────────
# These are plain String (not SecureString) — IPs are not secret.
resource "aws_ssm_parameter" "monitoring_server_ip" {
  name  = "/lgtm/monitoring_server_ip"
  type  = "String"
  value = aws_eip.monitoring.public_ip
}

resource "aws_ssm_parameter" "monitoring_server_public_ip" {
  name  = "/lgtm/monitoring_server_public_ip"
  type  = "String"
  value = aws_eip.monitoring.public_ip
}

# ── Cross-server security group rules ─────────────────────────────────────────
# The app server already exists, so Terraform only opens monitoring-server
# ingestion ports to the configured app server CIDR.

# Monitoring server: receive OTLP traces from app server (Tempo)
resource "aws_security_group_rule" "monitoring_otlp_grpc" {
  security_group_id = aws_security_group.monitoring.id
  type              = "ingress"
  description       = "OTLP gRPC from app server"
  from_port         = 4317
  to_port           = 4317
  protocol          = "tcp"
  cidr_blocks       = [var.app_server_source_cidr]
}

# Monitoring server: receive OTLP HTTP from app server (Tempo)
resource "aws_security_group_rule" "monitoring_otlp_http" {
  security_group_id = aws_security_group.monitoring.id
  type              = "ingress"
  description       = "OTLP HTTP from app server"
  from_port         = 4318
  to_port           = 4318
  protocol          = "tcp"
  cidr_blocks       = [var.app_server_source_cidr]
}

# Monitoring server: receive OTLP logs from app server (Loki)
resource "aws_security_group_rule" "monitoring_loki_otlp" {
  security_group_id = aws_security_group.monitoring.id
  type              = "ingress"
  description       = "Loki OTLP push from app server"
  from_port         = 3100
  to_port           = 3100
  protocol          = "tcp"
  cidr_blocks       = [var.app_server_source_cidr]
}

# ── Bootstrap: configure the existing app server monitoring agent ─────────────
resource "null_resource" "bootstrap_app" {
  triggers = {
    app_server_ssh_host       = var.app_server_ssh_host
    app_server_metrics_host   = var.app_server_metrics_host
    app_server_app_port       = tostring(var.app_server_app_port)
    monitoring_server_public  = aws_eip.monitoring.public_ip
    app_agent_script_checksum = filesha256("../scripts/app-agent.sh")
  }

  depends_on = [
    aws_ssm_parameter.monitoring_server_ip,
    null_resource.bootstrap,
  ]

  connection {
    type        = "ssh"
    user        = var.app_server_ssh_user
    private_key = var.app_server_ssh_password == "" ? file(var.ssh_private_key_path) : null
    password    = var.app_server_ssh_password == "" ? null : var.app_server_ssh_password
    host        = var.app_server_ssh_host
    timeout     = "10m"
  }

  provisioner "remote-exec" {
    inline = ["cloud-init status --wait || true"]
  }

  provisioner "file" {
    source      = "../scripts/app-agent.sh"
    destination = "/tmp/app-agent.sh"
  }

  provisioner "remote-exec" {
    inline = [
      "chmod +x /tmp/app-agent.sh",
      "printf '%s\\n' '${var.app_server_ssh_password}' | sudo -S -p '' env MONITORING_SERVER_IP='${aws_eip.monitoring.public_ip}' APP_PORT='${var.app_server_app_port}' APP_LOG_FILE='${var.app_server_app_log_file}' APP_ERROR_LOG_FILE='${var.app_server_app_error_log_file}' bash /tmp/app-agent.sh",
      "rm -f /tmp/app-agent.sh"
    ]
  }
}
