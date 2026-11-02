# OpenSSH on a small EC2 instance (ADR 0001). Partners log in as a chrooted, key-only SFTP user.
# Admin access is through SSM Session Manager, so no admin SSH key exists.

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "tls_private_key" "sftp" {
  algorithm = "ED25519"
}

resource "aws_security_group" "sftp" {
  name        = "${local.p}-sftp"
  description = "SFTP server for the RetailPulse 3PL and supplier feeds"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "sftp" {
  for_each          = toset(var.sftp_ingress_cidrs)
  security_group_id = aws_security_group.sftp.id
  cidr_ipv4         = each.value
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}

# Outbound HTTPS for package updates, SSM and publishing the host's public IP.
resource "aws_vpc_security_group_egress_rule" "sftp_https" {
  security_group_id = aws_security_group.sftp.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "sftp_http" {
  security_group_id = aws_security_group.sftp.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_iam_role" "sftp" {
  name = "${local.p}-sftp"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sftp_ssm" {
  role       = aws_iam_role.sftp.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Without an Elastic IP (which costs money while the instance is stopped) the public IP changes
# on every start, so the instance publishes its current address to Parameter Store at boot.
resource "aws_iam_role_policy" "sftp_publish_host" {
  name = "publish-host"
  role = aws_iam_role.sftp.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:PutParameter"
      Resource = aws_ssm_parameter.sftp_host.arn
    }]
  })
}

resource "aws_iam_instance_profile" "sftp" {
  name = "${local.p}-sftp"
  role = aws_iam_role.sftp.name
}

resource "aws_instance" "sftp" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.value
  instance_type               = var.sftp_instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.sftp.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.sftp.name

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  user_data = templatefile("${path.module}/sftp_user_data.sh.tftpl", {
    sftp_user  = "retailpulse"
    public_key = trimspace(tls_private_key.sftp.public_key_openssh)
    host_param = aws_ssm_parameter.sftp_host.name
    region     = local.region
  })
  user_data_replace_on_change = true

  tags = {
    Name = "${local.p}-sftp"
  }

  lifecycle {
    # A newer AMI should not replace a running server; patch it in place instead.
    ignore_changes = [ami]
  }
}
