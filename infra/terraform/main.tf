terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "isli-terraform-state"
    key    = "isli/terraform.tfstate"
    region = "eu-west-1"
  }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source = "./modules/networking"

  vpc_cidr       = var.vpc_cidr
  azs            = var.availability_zones
  public_subnets = var.public_subnets
  private_subnets = var.private_subnets
}

module "iam" {
  source = "./modules/iam"
}

module "database" {
  source = "./modules/database"

  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  db_name            = var.db_name
  db_username        = var.db_username
  db_password        = var.db_password
}

module "cache" {
  source = "./modules/cache"

  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
}

module "compute" {
  source = "./modules/compute"

  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  private_subnet_ids = module.networking.private_subnet_ids
  iam_role_arn      = module.iam.ecs_task_role_arn

  core_api_image    = var.core_api_image
  keeper_image      = var.keeper_image
  channels_image    = var.channels_image
  skills_image      = var.skills_image
  board_image       = var.board_image
}
