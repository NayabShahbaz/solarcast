#!/usr/bin/env bash
# [Member 3] Pull an image tag from ECR and (re)start the API on EC2.
# Usage: ./scripts/deploy_ec2.sh <image_tag>
set -euo pipefail
TAG="${1:?image tag required}"
echo "TODO: docker pull \$ECR_URI:$TAG && restart container, record tag in /opt/solarcast/current_tag"
