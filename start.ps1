# start.ps1 - Boot Career Platform on Windows (offline-friendly)

# 1️⃣ Load .env into process env vars
if (Test-Path .\.env) {
    Get-Content .\.env |
      Where-Object { $_ -and -not $_.StartsWith('#') } |
      ForEach-Object {
        $parts = $_ -split '=',2
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
      }
}

# 2️⃣ Activate the Python virtual environment
if (Test-Path .\venv\Scripts\Activate.ps1) {
    . .\venv\Scripts\Activate.ps1
} else {
    Write-Warning 'Virtual environment not found. Please run "python -m venv venv" first.'
}

# 3️⃣ Install dependencies from vendor only (no PyPI)
#    This makes pip look in vendor/ for wheels to satisfy requirements.txt
Write-Host "Installing dependencies from vendor/"
pip install --no-index --find-links vendor -r requirements.txt

# 4️⃣ Run test suite (optional – won’t block launch if tests fail or skip)
Write-Host "Running test suite..."
try {
    python -m pytest -q
} catch {
    Write-Warning "Tests failed or were skipped. Continuing to start the app..."
}

# 5️⃣ Launch the Flask application
Write-Host "Starting Flask app..."
python -m career_platform.app
