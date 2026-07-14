from django.apps import AppConfig


class T12MappingConfig(AppConfig):
    name = 't12_mapping'

    def ready(self):
        # The T12 pipeline owns its own file logging (config/logging.json → app/logs/t12.log).
        from t12_pipeline.config.log_config import configure_logging
        configure_logging()
