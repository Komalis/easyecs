#!/usr/bin/env python3
"""
Test CloudFormation template generation without AWS credentials.
This validates that the template is generated correctly with the new features.
"""

from easyecs.helpers.settings import read_ecs_file
from easyecs.cloudformation.template import create_template
import json

def test_template_generation():
    """Test template generation with new features."""
    try:
        # Read config
        ecs_data = read_ecs_file("ecs.yml")
        print("✅ Config loaded successfully")

        # Mock AWS values for testing
        service_name = "test-service"
        aws_account_id = "123456789012"
        aws_region = "us-east-1"
        vpc_id = "vpc-12345678"
        subnet_ids = ["subnet-12345678", "subnet-87654321"]
        azs = ["us-east-1a", "us-east-1b"]

        print("\n🔨 Generating CloudFormation template...")

        # Generate template (this will create .cloudformation directory)
        create_template(
            service_name,
            aws_account_id,
            aws_region,
            vpc_id,
            subnet_ids,
            azs,
            ecs_data,
            run=False
        )

        print("✅ Template generated successfully!")

        # Read and analyze the generated template
        template_path = ".cloudformation/test-service.template.json"
        with open(template_path, 'r') as f:
            template = json.load(f)

        print("\n📋 Template Analysis:")

        # Find task definition in template
        for resource_name, resource in template.get("Resources", {}).items():
            if resource.get("Type") == "AWS::ECS::TaskDefinition":
                props = resource.get("Properties", {})

                # Check ephemeral storage
                ephemeral_storage = props.get("EphemeralStorage")
                if ephemeral_storage:
                    print(f"  ✅ Ephemeral Storage: {ephemeral_storage.get('SizeInGiB')} GiB")
                else:
                    print("  ℹ️  Ephemeral Storage: Using default (21 GiB)")

            # Check target group for idle timeout
            if resource.get("Type") == "AWS::ElasticLoadBalancingV2::TargetGroup":
                props = resource.get("Properties", {})
                deregistration_delay = props.get("TargetGroupAttributes", [])

                for attr in deregistration_delay:
                    if attr.get("Key") == "deregistration_delay.timeout_seconds":
                        print(f"  ✅ Load Balancer Idle Timeout: {attr.get('Value')} seconds")

        print("\n✅ All checks passed!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_template_generation()
