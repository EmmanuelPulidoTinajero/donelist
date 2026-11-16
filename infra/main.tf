data "aws_vpc" "default" {
  default = true
}

# The AMI is looked up instead of hardcoded: the Learner Lab resets, and a stale
# AMI id in a workflow variable is a failure nobody can see coming.
data "aws_ami" "app" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.1-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# The key pair is provisioned by Terraform: the private half stays in state and
# is exposed only through the sensitive ssh_private_key_pem output.
resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "app" {
  key_name   = "${var.project_name}-key"
  public_key = tls_private_key.ssh.public_key_openssh

  tags = {
    Name = "${var.project_name}-key"
  }
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "app" {
  id = data.aws_subnets.default.ids[0]
}

# RDS rejects '/', '@', '"' and space in MasterUserPassword, so the alphabet is
# restricted to characters it accepts. Keeping the special set explicit avoids
# an apply that fails only once the database creation is attempted.
resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_security_group" "app" {
  name        = "${var.project_name}-app"
  description = "Allow API traffic to the EC2 application"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "API"
    from_port   = var.app_port
    to_port     = var.app_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Delivery runs over SSM Run Command and interactive access over SSM Session
  # Manager, so port 22 stays closed unless someone asks for it explicitly.
  dynamic "ingress" {
    for_each = var.ssh_cidr == null ? [] : [var.ssh_cidr]

    content {
      description = "SSH, only when ssh_cidr is supplied"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name        = "${var.project_name}-db"
  description = "Allow PostgreSQL only from the application security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "PostgreSQL from EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "db" {
  name       = var.project_name
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "db" {
  identifier             = var.project_name
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = var.db_name
  username               = var.db_username
  password               = random_password.db.result
  port                   = 5432
  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  skip_final_snapshot    = true
  deletion_protection    = false
}

resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.project_name}/database"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    host     = aws_db_instance.db.address
    port     = 5432
    database = var.db_name
    username = var.db_username
    password = random_password.db.result
  })
}

resource "aws_instance" "app" {
  ami                         = data.aws_ami.app.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnet.app.id
  vpc_security_group_ids      = [aws_security_group.app.id]
  key_name                    = aws_key_pair.app.key_name
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = true
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repository_url    = var.repository_url
    repository_branch = var.repository_branch
    secret_arn        = aws_secretsmanager_secret.db.arn
    aws_region        = var.aws_region
    app_version       = var.app_version
    app_port          = var.app_port
  })

  tags = {
    Name = var.project_name
  }

  # The AMI is resolved by a *most_recent* data source, so a new Amazon Linux
  # image would otherwise make every later apply plan an instance replacement:
  # unplanned downtime and a new public IP that invalidates API_URL. Replacing
  # the instance is a deliberate act, done by tainting or renaming it.
  lifecycle {
    ignore_changes = [ami]
  }

  depends_on = [aws_secretsmanager_secret_version.db]
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Terraform only attaches an inline policy to the lab's existing role: it never
# creates an IAM role, which the learned lab forbids.
data "aws_iam_role" "instance" {
  count = var.instance_role_name == "" ? 0 : 1
  name  = var.instance_role_name
}

resource "aws_iam_role_policy" "cloudwatch_put_metric_data" {
  count = var.instance_role_name == "" ? 0 : 1
  name  = "${var.project_name}-cloudwatch-put-metric-data"
  role  = data.aws_iam_role.instance[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["cloudwatch:PutMetricData"]
      Resource = "*"
    }]
  })
}

# Metric 1 — native AWS/RDS metric, nothing to instrument.
resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name          = "${var.project_name}-database-connections"
  alarm_description   = "RDS connections in use are approaching the instance limit."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.db.identifier }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.database_connections_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Metric 2 — failed RDS reads counted by the API and published with boto3.
resource "aws_cloudwatch_metric_alarm" "db_read_errors" {
  alarm_name          = "${var.project_name}-db-read-errors"
  alarm_description   = "The API cannot read from RDS; investigate the database instance."
  namespace           = "ToDoListApi"
  metric_name         = "DbReadErrors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Metric 2 (write side) — failed RDS inserts counted by the API.
resource "aws_cloudwatch_metric_alarm" "db_write_errors" {
  alarm_name          = "${var.project_name}-db-write-errors"
  alarm_description   = "The API cannot write to RDS; created tasks are being lost."
  namespace           = "ToDoListApi"
  metric_name         = "DbWriteErrors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Metric 3 — proposed behavior metric: task intake throughput.
resource "aws_cloudwatch_metric_alarm" "tasks_created" {
  alarm_name          = "${var.project_name}-tasks-created"
  alarm_description   = "Task creation burst: unusual traffic or a retry loop hammering POST /tasks."
  namespace           = "ToDoListApi"
  metric_name         = "TasksCreated"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 50
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
