#!/usr/bin/env python3
"""
Quick validation script to test that your ecs.yml config is valid
without deploying to AWS.
"""

from easyecs.helpers.settings import read_ecs_file


def test_config():
    """Test that the config file is valid."""
    try:
        ecs_data = read_ecs_file("ecs.yml")

        print("✅ Config file is valid!")
        print("\n📋 Configuration Summary:")
        print(f"  App name: {ecs_data.metadata.appname}")

        # Test ephemeral storage
        if ecs_data.task_definition.ephemeral_storage:
            print(
                f"  Ephemeral storage: {ecs_data.task_definition.ephemeral_storage} GiB"
            )
        else:
            print("  Ephemeral storage: 21 GiB (default)")

        # Test load balancer idle timeout
        if ecs_data.load_balancer:
            if ecs_data.load_balancer.idle_timeout:
                print(
                    f"  LB idle timeout: {ecs_data.load_balancer.idle_timeout} seconds"
                )
            else:
                print("  LB idle timeout: 300 seconds (default)")

        print("\n✅ All validations passed!")
        return True

    except ValueError as e:
        print(f"❌ Validation error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    test_config()
