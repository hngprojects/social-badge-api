output "monitoring_server_ip" {
  value       = aws_eip.monitoring.public_ip
  description = "Static public IP of the monitoring server (Elastic IP — will not change on restart)"
}

output "grafana_url" {
  value       = "http://${aws_eip.monitoring.public_ip}:3000"
  description = "Grafana dashboard — login: admin / <grafana_admin_password>"
}

output "grafana_domain_url" {
  value       = "http://${var.duckdns_subdomain}.duckdns.org:3000"
  description = "Public Grafana dashboard URL using DuckDNS"
}

output "prometheus_url" {
  value = "http://${aws_eip.monitoring.public_ip}:9090"
}

output "prometheus_domain_url" {
  value = "http://${var.duckdns_subdomain}.duckdns.org:9090"
}

output "alertmanager_url" {
  value = "http://${aws_eip.monitoring.public_ip}:9093"
}

output "alertmanager_domain_url" {
  value = "http://${var.duckdns_subdomain}.duckdns.org:9093"
}

output "monitoring_domain" {
  value       = "${var.duckdns_subdomain}.duckdns.org"
  description = "DuckDNS domain pointing at the monitoring server"
}

output "loki_url" {
  value = "http://${aws_eip.monitoring.public_ip}:3100"
}

output "tempo_url" {
  value = "http://${aws_eip.monitoring.public_ip}:3200"
}

output "pushgateway_url" {
  value       = "http://${aws_eip.monitoring.public_ip}:9091"
  description = "Push DORA metrics here from GitHub Actions — store as PUSHGATEWAY_URL secret"
}

# ── GitHub Actions secrets ─────────────────────────────────────────────────────
# Run `terraform output github_actions_secrets` after apply to get the exact
# values to paste into: GitHub repo → Settings → Secrets and variables → Actions
output "github_actions_secrets" {
  value = {
    MONITOR_SERVER_IP = aws_eip.monitoring.public_ip
    PUSHGATEWAY_URL   = "http://${aws_eip.monitoring.public_ip}:9091"
  }
  description = "Values to store as GitHub Actions secrets. MONITOR_SSH_KEY must be set manually (private key content)."
}

output "ssh_command" {
  value = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_eip.monitoring.public_ip}"
}

output "otlp_grpc_endpoint" {
  value       = "${aws_eip.monitoring.public_ip}:4317"
  description = "Tempo OTLP gRPC endpoint — app server OTel Collector forwards traces here"
}

output "app_ssh_command" {
  value       = "ssh -i ${var.ssh_private_key_path} ${var.app_server_ssh_user}@${var.app_server_ssh_host}"
  description = "SSH into the existing application server"
}

output "app_metrics_url" {
  value       = "http://${var.app_server_metrics_host}:${var.app_server_app_port}/metrics"
  description = "Existing app server metrics endpoint scraped by Prometheus"
}

output "app_health_url" {
  value       = "http://${var.app_server_metrics_host}:${var.app_server_app_port}/api/v1/health"
  description = "Existing app server health endpoint probed by Blackbox"
}
