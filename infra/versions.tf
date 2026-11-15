terraform {
  required_version = ">= 1.10.0"

  # The state lives in S3, never in the repository. Encryption and native S3
  # state locking (use_lockfile) are declared here so a plain
  # `terraform init -backend-config=...` cannot forget them.
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
