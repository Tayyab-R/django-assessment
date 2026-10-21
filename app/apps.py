from django.apps import AppConfig


class AppConfig(AppConfig):
    name = 'app'

    def ready(self):
        try:
            from app.stations import load_stations
            from app.locations import load_places
            load_stations()
            load_places()
            
        except FileNotFoundError:
            pass # Run the build_stations management command in terminal