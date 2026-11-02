.PHONY: install lint test generate generate-small clean \
	infra-bootstrap infra-init infra-plan infra-apply infra-destroy sources-up sources-down

TF_DEV := terraform -chdir=infra/terraform/envs/dev
REGION := us-east-1

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .
	terraform -chdir=infra/terraform fmt -recursive -check

test:
	pytest -q

# Generate the default dataset (90 days) into ./output
generate:
	python -m data_generator.simulate --out output

# Small dataset for a quick look
generate-small:
	python -m data_generator.simulate --out output --scale 0.05 --days 14

clean:
	rm -rf output .pytest_cache .ruff_cache

# --- AWS sources (Terraform). Needs `aws configure` and Terraform 1.10+.

# Once per account: the S3 bucket that holds Terraform state.
infra-bootstrap:
	terraform -chdir=infra/terraform/bootstrap init
	terraform -chdir=infra/terraform/bootstrap apply

infra-init:
	$(TF_DEV) init -backend-config=backend.hcl

infra-plan:
	$(TF_DEV) plan -out=dev.tfplan

infra-apply:
	$(TF_DEV) apply dev.tfplan

# Removes every source system and its data. The state bucket from infra-bootstrap stays.
infra-destroy:
	$(TF_DEV) destroy

# Start or stop RDS and the SFTP server outside the daily window.
sources-up:
	aws rds start-db-instance --region $(REGION) --db-instance-identifier retailpulse-dev-orders
	aws ec2 start-instances --region $(REGION) --instance-ids $$($(TF_DEV) output -json sources | python -c "import json,sys; print(json.load(sys.stdin)['sftp_instance_id'])")

sources-down:
	aws rds stop-db-instance --region $(REGION) --db-instance-identifier retailpulse-dev-orders
	aws ec2 stop-instances --region $(REGION) --instance-ids $$($(TF_DEV) output -json sources | python -c "import json,sys; print(json.load(sys.stdin)['sftp_instance_id'])")
