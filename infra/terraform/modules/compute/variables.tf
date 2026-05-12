variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "iam_role_arn" {
  type = string
}

variable "core_api_image" {
  type = string
}

variable "keeper_image" {
  type = string
}

variable "channels_image" {
  type = string
}

variable "skills_image" {
  type = string
}

variable "board_image" {
  type = string
}
