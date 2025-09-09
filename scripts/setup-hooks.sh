#!/usr/bin/env bash
# Setup pre-commit framework for cr8tor

set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "Setting up pre-commit framework for cr8tor..."

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo "Installing pre-commit framework..."
    pip install pre-commit
fi

# Install the hooks
pre-commit install

# Test the setup
echo "Testing pre-commit hooks..."
export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH}"

# Run the CRD validation hook manually
python3 -c "
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

try:
    from cr8tor.crd.generator import KareCRDManager
    manager = KareCRDManager()
    manager.registry.discover_models()
    models = manager.registry.get_all_models()
    crds = manager.get_crds_as_dict()
    print(f'Pre-commit test: {len(models)} models, {len(crds)} CRDs validated')
except Exception as e:
    print(f'Pre-commit test failed: {e}')
    sys.exit(1)
"

echo "Pre-commit setup complete!"
echo ""
echo "Pre-commit will automatically run:"
echo "  • YAML validation"
echo "  • Python linting (ruff)"
echo "  • Python formatting (ruff-format)"
echo "  • CRD model validation"
echo "  • Security checks"
echo ""
echo "Commands:"
echo "  pre-commit run --all-files  # Run on all files"
echo "  pre-commit run              # Run on staged files"
echo "  git commit --no-verify      # Skip hooks temporarily"
