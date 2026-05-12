resource "aws_db_subnet_group" "main" {
  name       = "isli-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "isli-db-subnet-group"
  }
}

resource "aws_security_group" "postgres" {
  name_prefix = "isli-postgres-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier             = "isli-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.medium"
  allocated_storage      = 100
  max_allocated_storage  = 500
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  publicly_accessible    = false
  multi_az               = true
  storage_encrypted      = true
  skip_final_snapshot    = true

  tags = {
    Name = "isli-postgres"
  }
}
