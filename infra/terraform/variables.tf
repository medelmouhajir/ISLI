variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
}

variable "public_subnets" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnets" {
  description = "Private subnet CIDRs"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "isli"
}

variable "db_username" {
  description = "PostgreSQL username"
  type        = string
  default     = "isli"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "core_api_image" {
  description = "Core API Docker image"
  type        = string
}

variable "keeper_image" {
  description = "Keeper Docker image"
  type        = string
}

variable "channels_image" {
  description = "Channels Docker image"
  type        = string
}

variable "skills_image" {
  description = "Skills Docker image"
  type        = string
}

variable "board_image" {
  description = "Board Docker image"
  type        = string
}
