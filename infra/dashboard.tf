data "aws_region" "current" {}

# The dashboard renders the three instrumented metrics: the native AWS/RDS
# metric, the two API counters published with boto3, and the state of every
# alarm wired to the SNS topic.
resource "aws_cloudwatch_dashboard" "api" {
  dashboard_name = "${var.project_name}-api"

  dashboard_body = templatefile("${path.module}/dashboard.json.tftpl", {
    region                = data.aws_region.current.name
    db_instance           = aws_db_instance.db.identifier
    connections_threshold = var.database_connections_threshold
    native_alarm          = aws_cloudwatch_metric_alarm.database_connections.arn
    read_errors_alarm     = aws_cloudwatch_metric_alarm.db_read_errors.arn
    write_errors_alarm    = aws_cloudwatch_metric_alarm.db_write_errors.arn
    tasks_created_alarm   = aws_cloudwatch_metric_alarm.tasks_created.arn
  })
}
