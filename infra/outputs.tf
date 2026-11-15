output "api_url" {
  value = "http://${aws_instance.app.public_ip}:${var.app_port}"
}

output "instance_public_ip" {
  value = aws_instance.app.public_ip
}

output "database_endpoint" {
  value     = aws_db_instance.db.address
  sensitive = true
}

output "database_secret_arn" {
  value     = aws_secretsmanager_secret.db.arn
  sensitive = true
}

output "alerts_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "SNS topic wired to the three CloudWatch alarms."
}

output "alarm_names" {
  value = [
    aws_cloudwatch_metric_alarm.database_connections.alarm_name,
    aws_cloudwatch_metric_alarm.db_read_errors.alarm_name,
    aws_cloudwatch_metric_alarm.db_write_errors.alarm_name,
    aws_cloudwatch_metric_alarm.tasks_created.alarm_name,
  ]
  description = "CloudWatch alarms created, one per published metric."
}

output "dashboard_name" {
  value       = aws_cloudwatch_dashboard.api.dashboard_name
  description = "CloudWatch dashboard rendering the three instrumented metrics."
}

output "key_pair_name" {
  value       = aws_key_pair.app.key_name
  description = "EC2 key pair created by Terraform."
}

output "ssh_private_key_pem" {
  value       = tls_private_key.ssh.private_key_pem
  description = "Private key matching the generated key pair. Read it with: terraform output -raw ssh_private_key_pem > key.pem"
  sensitive   = true
}
