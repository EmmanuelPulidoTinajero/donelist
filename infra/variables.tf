variable "aws_region" {
  description = "AWS region used by the learned lab."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for resource names."
  type        = string
  default     = "to-do-list-api"
}

variable "repository_url" {
  description = "Public Git repository cloned by EC2 user_data."
  type        = string
}

variable "instance_profile_name" {
  description = "Existing EC2 instance profile backed by the lab's single allowed IAM role. Terraform does not create IAM roles."
  type        = string
}

variable "ami_id" {
  description = "Amazon Linux 2023 AMI ID for the selected region."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t2.micro"
}

variable "ssh_cidr" {
  description = "CIDR allowed to SSH to EC2. Required, with no default: the deploy workflow connects from GitHub-hosted runners, so allow those ranges or the addresses you actually use."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0))
    error_message = "ssh_cidr must be a valid CIDR block, such as 203.0.113.10/32."
  }
}

variable "app_port" {
  description = "Port exposed by the API."
  type        = number
  default     = 3000
}

variable "db_name" {
  type    = string
  default = "tasks"
}

variable "db_username" {
  type    = string
  default = "tasks_app"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "app_version" {
  type    = string
  default = "1.0.0"
}

variable "alert_email" {
  description = "Email address subscribed to the SNS topic wired to every CloudWatch alarm."
  type        = string
}

variable "instance_role_name" {
  description = "Existing IAM role behind the EC2 instance profile. When set, Terraform attaches an inline policy granting cloudwatch:PutMetricData; Terraform still creates no IAM role."
  type        = string
  default     = ""
}

variable "database_connections_threshold" {
  description = "Simultaneous connections before the native AWS/RDS DatabaseConnections alarm fires."
  type        = number
  default     = 20
}
