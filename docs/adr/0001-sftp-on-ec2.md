# ADR 0001: Run the SFTP source on a small EC2 instance

Status: accepted, 2026-10-27

## Context

The project needs an SFTP source that partners push files to and the platform pulls from. AWS Transfer Family is the managed option, but it bills for every hour the endpoint exists (about $0.30 per hour per protocol at the time of writing, roughly $216 a month), which is a lot for a portfolio project.

## Decision

Run OpenSSH on a small EC2 instance and stop it when idle. Terraform keeps an optional switch to create a Transfer Family endpoint instead.

## Consequences

- Cost is a few dollars a month while the instance runs, and almost nothing while it is stopped.
- We patch and secure the instance ourselves: key-only login, a security group limited to known IP ranges, and a chrooted SFTP user.
- The ingestion job is the same either way, because it only speaks SFTP.
