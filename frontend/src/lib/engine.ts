export const ENGINE_START_COMMAND = 'python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000'

export const ENGINE_ACTIVATION_COMMANDS = {
  powershell: '.\\.venv\\Scripts\\Activate.ps1',
  posix: 'source .venv/bin/activate',
} as const
