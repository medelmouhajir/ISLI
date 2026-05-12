locals {
  services = {
    core_api = {
      name     = "core-api"
      port     = 8000
      cpu      = "1024"
      memory   = "2048"
      image    = var.core_api_image
      public   = false
      path     = "/api/*"
      priority = 10
      health_path = "/health"
    }
    keeper = {
      name     = "keeper"
      port     = 8001
      cpu      = "512"
      memory   = "1024"
      image    = var.keeper_image
      public   = false
      path     = "/keeper/*"
      priority = 20
      health_path = "/health"
    }
    channels = {
      name     = "channels"
      port     = 8002
      cpu      = "512"
      memory   = "1024"
      image    = var.channels_image
      public   = false
      path     = "/channels/*"
      priority = 30
      health_path = "/health"
    }
    skills = {
      name     = "skills"
      port     = 8003
      cpu      = "512"
      memory   = "1024"
      image    = var.skills_image
      public   = false
      path     = "/skills/*"
      priority = 40
      health_path = "/health"
    }
    board = {
      name     = "board"
      port     = 80
      cpu      = "256"
      memory   = "512"
      image    = var.board_image
      public   = true
      path     = "/"
      priority = 100
      health_path = "/"
    }
  }
}

resource "aws_ecs_cluster" "main" {
  name = "isli-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_security_group" "alb" {
  name_prefix = "isli-alb-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "isli-ecs-"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "main" {
  name               = "isli-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "services" {
  for_each = local.services

  name        = "isli-${each.value.name}"
  port        = each.value.port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = each.value.name == "board" ? "/" : "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["board"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  for_each = {
    for k, v in local.services : k => v
    if k != "board"
  }

  listener_arn = aws_lb_listener.http.arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services[each.key].arn
  }

  condition {
    path_pattern {
      values = [each.value.path]
    }
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  for_each = local.services

  name              = "/ecs/isli-${each.value.name}"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "services" {
  for_each = local.services

  family                   = "isli-${each.value.name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = var.iam_role_arn
  task_role_arn            = var.iam_role_arn

  container_definitions = jsonencode([{
    name      = each.value.name
    image     = each.value.image
    essential = true
    portMappings = [{
      containerPort = each.value.port
      protocol      = "tcp"
    }]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${each.value.port}${each.value.health_path} || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs[each.key].name
        awslogs-region        = "eu-west-1"
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "services" {
  for_each = local.services

  name            = "isli-${each.value.name}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.services[each.key].arn
  desired_count   = each.value.name == "board" ? 2 : 3
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = each.value.public ? var.public_subnet_ids : var.private_subnet_ids
    assign_public_ip = each.value.public
    security_groups  = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.services[each.key].arn
    container_name   = each.value.name
    container_port   = each.value.port
  }

  deployment_controller {
    type = "ECS"
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  depends_on = [aws_lb_listener.http]
}
