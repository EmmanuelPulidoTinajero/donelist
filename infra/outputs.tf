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
