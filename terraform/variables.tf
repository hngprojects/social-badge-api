# ── AWS infrastructure ─────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy the monitoring server"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type for the monitoring server (t3.large is the minimum for the full LGTM stack)"
  type        = string
  default     = "t3.large"
}

variable "ssh_public_key_path" {
  description = "Local path to the public key to import into AWS as a key pair"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_private_key_path" {
  description = "Local path to the matching private key — Terraform uses this to SSH in and run lgtm-stack.sh"
  type        = string
  default     = "~/.ssh/id_ed25519"
}

variable "engineer_ips" {
  description = "CIDR blocks for engineers allowed SSH + dashboard access (e.g. [\"203.0.113.1/32\"])"
  type        = list(string)
}

variable "public_monitoring_cidrs" {
  description = "CIDR blocks allowed to access the public monitoring UI/domain. Use [\"0.0.0.0/0\"] to allow anyone."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ── Existing application server ───────────────────────────────────────────────

variable "app_server_ssh_host" {
  description = "Existing application server host/IP that Terraform SSHes into to run scripts/app-agent.sh"
  type        = string
}

variable "app_server_ssh_user" {
  description = "SSH user for the existing application server"
  type        = string
  default     = "ubuntu"
}

variable "app_server_ssh_password" {
  description = "SSH password for the existing application server. Leave empty to use ssh_private_key_path instead."
  type        = string
  sensitive   = true
  default     = ""
}

variable "app_server_source_cidr" {
  description = "CIDR for the existing app server as seen by the monitoring server, used to allow OTLP/Loki ingress (for one public IP, use x.x.x.x/32)"
  type        = string
}

variable "app_server_metrics_host" {
  description = "Host/IP Prometheus should use to scrape the existing app server"
  type        = string
}

variable "app_server_app_port" {
  description = "Port where the FastAPI app exposes /metrics and /api/v1/health"
  type        = number
  default     = 8000
}

variable "app_server_node_exporter_port" {
  description = "Port where node_exporter will expose host metrics on the existing app server"
  type        = number
  default     = 9100
}

variable "app_server_app_log_file" {
  description = "App log file path on the existing app server for OTel Collector filelog ingestion"
  type        = string
  default     = "/opt/social-badge-api/logs/app.log"
}

variable "app_server_app_error_log_file" {
  description = "App error log file path on the existing app server for OTel Collector filelog ingestion"
  type        = string
  default     = "/opt/social-badge-api/logs/app_errors.log"
}

# ── Observability stack config ─────────────────────────────────────────────────

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for alert notifications"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_channel" {
  description = "Slack channel name for alerts"
  type        = string
  default     = "#social-badge-devops-alerts"
}

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
}

variable "duckdns_subdomain" {
  description = "DuckDNS subdomain (without .duckdns.org)"
  type        = string
  default     = "adeshipo-lgtm"
}

variable "duckdns_token" {
  description = "DuckDNS token for SSL certificate provisioning"
  type        = string
  sensitive   = true
}

variable "metrics_retention" {
  description = "Prometheus metrics retention period"
  type        = string
  default     = "15d"
}

variable "logs_retention" {
  description = "Loki log retention in hours"
  type        = number
  default     = 360
}

variable "alert_email_recipients" {
  description = "Email recipients for Alertmanager notifications"
  type        = list(string)
}

variable "smtp_smarthost" {
  description = "SMTP smarthost for Alertmanager email alerts, e.g. smtp.gmail.com:587"
  type        = string
}

variable "smtp_from" {
  description = "From address for Alertmanager email alerts"
  type        = string
}

variable "smtp_auth_username" {
  description = "SMTP username for Alertmanager"
  type        = string
  sensitive   = true
}

variable "smtp_auth_password" {
  description = "SMTP password or app password for Alertmanager"
  type        = string
  sensitive   = true
}

variable "smtp_require_tls" {
  description = "Whether Alertmanager should require TLS for SMTP"
  type        = bool
  default     = true
}
