# EasyECS Tests

This directory contains all tests for the EasyECS project.

## Test Structure

```
tests/
├── test_cli.py                          # CLI integration tests (36 tests)
├── test_config_validation.py            # Quick config validation script
├── test_template_generation.py          # Template generation test (requires Node.js)
├── model/
│   ├── test_validation.py              # Pydantic model validation tests
│   └── test_new_features.py            # Tests for ephemeral_storage & idle_timeout
├── docker/
│   └── test_docker_command.py          # Docker build command tests (4 tests)
├── cloudformation/
│   ├── stack/
│   │   └── test_create.py              # Stack creation tests
│   ├── template/
│   │   ├── test_depends_on.py          # Container dependency tests (3 tests)
│   │   ├── test_efs.py                 # EFS volume tests (3 tests)
│   │   └── test_template_command.py    # Command config tests (2 tests)
│   └── test_update.py                  # Stack update tests
```

## Running Tests

### Run All Tests
```bash
poetry run pytest tests/ -v
```

### Run Specific Test Categories

**Unit tests (no AWS/Node required):**
```bash
poetry run pytest tests/model/ tests/docker/ tests/test_cli.py -v
```

**Model validation tests:**
```bash
poetry run pytest tests/model/test_validation.py -v
poetry run pytest tests/model/test_new_features.py -v
```

**Docker tests:**
```bash
poetry run pytest tests/docker/ -v
```

**CLI tests:**
```bash
poetry run pytest tests/test_cli.py -v
```

**CloudFormation tests (requires Node.js):**
```bash
poetry run pytest tests/cloudformation/ -v
```

### Quick Config Validation (No pytest needed)
```bash
poetry run python tests/test_config_validation.py
```

### Template Generation Test (Requires Node.js)
```bash
poetry run python tests/test_template_generation.py
```

## Test Coverage

Run tests with coverage:
```bash
poetry run pytest tests/ --cov=easyecs --cov-report=html
open htmlcov/index.html  # View coverage report
```

## New Features Tests

Tests for the newly added features (ephemeral storage and idle timeout):

**Location:** `tests/model/test_new_features.py`

**Run:**
```bash
poetry run pytest tests/model/test_new_features.py -v
```

**Coverage:**
- ✅ Ephemeral storage validation (21-200 GiB)
- ✅ Idle timeout validation (1-4000 seconds)
- ✅ Optional field handling (None = default)
- ✅ Error cases for out-of-range values

## Requirements

- **Python 3.11+**
- **Poetry** for dependency management
- **Node.js** (for CloudFormation template tests only)
- **AWS credentials** (for integration tests only)

## Notes

- Most tests use mocking and don't require AWS credentials
- CloudFormation template tests require Node.js for AWS CDK
- Use `test_config_validation.py` for quick validation without pytest
- Some tests may fail if Node.js is not installed (expected behavior)
