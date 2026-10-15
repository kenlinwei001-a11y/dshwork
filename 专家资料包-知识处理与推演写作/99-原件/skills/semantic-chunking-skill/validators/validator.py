def validate(output: dict) -> dict:
    required = ['project_id', 'document_id', 'version_id']
    missing = [k for k in required if k not in output]
    return {'status': 'FAIL' if missing else 'PASS', 'missing': missing}
