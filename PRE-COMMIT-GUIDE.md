# Pre-commit Hooks - User Guide

## What Are Pre-commit Hooks?

Pre-commit hooks run **automatically before every git commit**, catching code quality issues instantly instead of waiting for CI pipeline feedback.

## Installation (Already Done ✅)

```powershell
# Hooks are already installed in this project
# To verify:
pre-commit --version  # Should show: pre-commit 4.0.1
```

## Usage

### Automatic (Recommended)
Just commit as normal - hooks run automatically:

```powershell
git add services/customer_service/routes.py
git commit -m "feat: Add new customer endpoint"

# Hooks run automatically:
# ✅ Ruff Linter - Checking Python code...
# ✅ Black Formatter - Formatting code...
# ✅ Detect Secrets - Scanning for API keys...
# ✅ Check YAML - Validating syntax...

# If issues found, commit is BLOCKED
# Files are auto-fixed where possible
# Stage fixes and re-commit:
git add .
git commit -m "feat: Add new customer endpoint"
```

### Manual Run (Test Before Committing)

```powershell
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff-check --all-files
pre-commit run black --all-files
pre-commit run detect-secrets --all-files

# Run hooks on staged files only
pre-commit run
```

### Skip Hooks (Emergency Only)

```powershell
# Skip hooks for one commit (NOT RECOMMENDED)
git commit -m "WIP: Debug code" --no-verify

# Temporarily disable hooks
pre-commit uninstall

# Re-enable hooks
pre-commit install
```

## What Each Hook Does

### 1. Ruff Linter (`ruff-check`)
**Purpose**: Fast Python linter (replaces Flake8, Pylint, isort)  
**Action**: Auto-fixes issues like unused imports, line length violations  
**Config**: `.ruff.toml` (line-length=120, E/F rules)

**Example**:
```python
# Before commit:
import unused_module  # Will be removed
x = 1; y = 2  # Will suggest splitting to separate lines

# After hook:
x = 1
y = 2
```

### 2. Black Formatter (`black`)
**Purpose**: Opinionated Python code formatter  
**Action**: Auto-formats code to consistent style  
**Config**: `--line-length=120`

**Example**:
```python
# Before commit:
def my_function(arg1,arg2,arg3):
    return {"key":"value"}

# After hook:
def my_function(arg1, arg2, arg3):
    return {"key": "value"}
```

### 3. Detect Secrets (`detect-secrets`)
**Purpose**: Prevents committing API keys, passwords, tokens  
**Action**: **BLOCKS commit** if secrets detected  
**Config**: `.secrets.baseline` (allowlist for known false positives)

**Example**:
```python
# This will BLOCK commit:
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# Fix: Use environment variables
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")  # ✅ Passes hook
```

**Adding False Positives to Baseline**:
```powershell
# Update baseline to ignore specific files/lines
detect-secrets scan --baseline .secrets.baseline
```

### 4. YAML/JSON/TOML Syntax Checks
**Purpose**: Validates file syntax before commit  
**Action**: **BLOCKS commit** if syntax errors found

**Example**:
```yaml
# This will BLOCK commit:
invalid: yaml
  - missing: indent

# Fix:
invalid: yaml
  values:
    - correct: indent  # ✅ Passes hook
```

### 5. Trailing Whitespace & Line Endings
**Purpose**: Removes trailing spaces, enforces LF line endings (Unix-style)  
**Action**: Auto-fixes whitespace issues

### 6. Debug Statements Check
**Purpose**: Prevents committing debugger imports (`import pdb`, `breakpoint()`)  
**Action**: **BLOCKS commit** if found

**Example**:
```python
# This will BLOCK commit:
import pdb
pdb.set_trace()

# Fix: Remove before committing
# Or use: git commit --no-verify (NOT RECOMMENDED)
```

## Troubleshooting

### Hook Fails with "command not found"
**Cause**: Tool not installed in project venv  
**Fix**:
```powershell
.\venv\Scripts\Activate.ps1
pip install pre-commit ruff black detect-secrets
```

### "Permission denied" Error
**Cause**: Windows execution policy  
**Fix**:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Hook Too Slow
**Cause**: Running on large number of files  
**Fix**:
```powershell
# Run hooks only on staged files (faster)
pre-commit run

# Skip slow hooks temporarily
SKIP=detect-secrets git commit -m "message"
```

### Update Hook Versions
```powershell
# Update all hooks to latest versions
pre-commit autoupdate

# This updates .pre-commit-config.yaml automatically
```

## CI Integration

Pre-commit hooks also run in CI pipeline (`.github/workflows/ci.yml`). If you skip hooks locally with `--no-verify`, CI will still catch issues.

## Best Practices

1. ✅ **Run `pre-commit run --all-files` after pulling changes**
2. ✅ **Never use `--no-verify` except for emergencies**
3. ✅ **Update `.secrets.baseline` when adding legitimate test keys**
4. ✅ **Keep hooks fast** - avoid heavy analysis tools
5. ✅ **Educate team members** - share this guide with new developers

## Team Onboarding

When onboarding new team members:

```powershell
# 1. Clone repo
git clone https://github.com/VytasKer/Fintegrate.git
cd Fintegrate

# 2. Set up Python environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Install pre-commit hooks
pre-commit install

# 4. Test hooks
pre-commit run --all-files

# Done! Hooks will run automatically on every commit
```

## Comparison: With vs Without Pre-commit

### Without Pre-commit Hooks:
```
Developer commits bad code (2 seconds)
    ↓
Push to GitHub (5 seconds)
    ↓
CI pipeline starts (30 seconds)
    ↓
Linting fails (3 minutes)
    ↓
Developer fixes locally (2 minutes)
    ↓
Push again (5 seconds)
    ↓
CI runs again (3 minutes)
    ↓
Total: ~8 minutes + context switching cost
```

### With Pre-commit Hooks:
```
Developer tries to commit bad code (2 seconds)
    ↓
Hooks run locally (5 seconds)
    ↓
Auto-fix applied (instant)
    ↓
Developer adds fixes and re-commits (3 seconds)
    ↓
Push to GitHub (5 seconds)
    ↓
CI passes first time (3 minutes)
    ↓
Total: ~3 minutes, no context switching
```

**Time saved per commit: ~5 minutes**  
**Developer happiness: Significantly improved** ✨
