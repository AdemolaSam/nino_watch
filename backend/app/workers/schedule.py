# Celery Beat schedule. Verify entries land in B7.
beat_schedule: dict = {
    "ingest-all": {
        "task": "ninowatch.ingest_all",
        "schedule": 2700,  # every 45 minutes
    },
    "extract-pending": {
        "task": "ninowatch.extract_pending_all",
        "schedule": 600,  # every 10 minutes
    },
    "cluster-all": {
        "task": "ninowatch.cluster_all",
        "schedule": 900,  # every 15 minutes
    },
    "climate-all": {
        "task": "ninowatch.refresh_climate_all",
        "schedule": 21600,  # every 6 hours
    },
    "verify-pending": {
        "task": "ninowatch.verify_pending_all",
        "schedule": 1200,  # every 20 minutes
    },
    "advisories-all": {
        "task": "ninowatch.generate_advisories_all",
        "schedule": 86400,  # daily; verify also triggers on meaningful change
    },
}
