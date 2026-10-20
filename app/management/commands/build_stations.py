"""One-time data prep: python manage.py build_stations

Reads the fuel CSV + the GeoNames US postal file, and writes two committed files:
  app/data/stations.json  one record per US truck stop, with lat/lng
  app/data/places.json    one record per US place (used to resolve start/finish)
"""
import csv


import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.data_cleaning import clean_fuel_data, normalize_city


class Command(BaseCommand):
    help = "Clean the fuel CSV, geocode it offline with GeoNames, write stations.json and places.json"

    def handle(self, *args, **options):
        data_dir = settings.BASE_DIR / "app" / "data"
        csv_path = data_dir / "fuel-prices-for-be-assessment.csv"
        geonames_path = data_dir / "US.txt"

        for path in (csv_path, geonames_path):
            if not path.exists():
                raise CommandError(f"Missing input file: {path}")

        # Clean the fuel data (US only, one row per stop, lowest price)
        stations_data = clean_fuel_data(str(csv_path))
        self.stdout.write(f"clean stops: {len(stations_data)}")

        # Load GeoNames tab-separated, no header, quotes are plain text
        us_geonames = pd.read_csv(
            geonames_path,
            sep="\t",
            header=None,
            usecols=[2, 4, 9, 10],
            names=["place", "state", "lat", "lng"],
            quoting=csv.QUOTE_NONE,
            keep_default_na=False,
        )
        us_geonames["state"] = us_geonames["state"].str.strip().str.upper()
        us_geonames = us_geonames[us_geonames["state"] != ""]
        us_geonames["city_key"] = us_geonames["place"].map(normalize_city)

        # One point per (city, state): average of that place's ZIP rows
        us_geo = us_geonames.groupby(["city_key", "state"], as_index=False)[
            ["lat", "lng"]
        ].mean()
        raw_pairs = us_geonames[["place", "state"]].drop_duplicates().shape[0]
        self.stdout.write(f"places: {raw_pairs} raw pairs -> {len(us_geo)} keys")

        # attach coordinates left join so failures stay visible.
        stations = stations_data.merge(us_geo, on=["city_key", "state"], how="left")
        missing = stations[stations["lat"].isna()]
        self.stdout.write(f"{len(missing)} of {len(stations)} stations unmatched")
        if len(missing):
            self.stdout.write(
                str(missing[["city", "state"]].drop_duplicates().head(20).to_string())
            )
        stations = stations.dropna(subset=["lat", "lng"])

        # Sanity check: everything must sit inside the continental US box.
        lat_min, lat_max = stations["lat"].min(), stations["lat"].max()
        lng_min, lng_max = stations["lng"].min(), stations["lng"].max()
        self.stdout.write(f"lat {lat_min:.4f}..{lat_max:.4f}  lng {lng_min:.4f}..{lng_max:.4f}")
        outside = stations[
            ~stations["lat"].between(24, 50) | ~stations["lng"].between(-125, -66)
        ]
        if len(outside):
            self.stdout.write(self.style.WARNING(f"{len(outside)} stations outside the US box:"))
            self.stdout.write(outside[["city", "state", "lat", "lng"]].head(20).to_string())

        # Write the files the API will load
        station_cols = ["stop_id", "name", "city", "state", "price", "lat", "lng"]
        out = stations[station_cols].copy()
        out["price"] = out["price"].round(4)
        out[["lat", "lng"]] = out[["lat", "lng"]].round(5)
        out.to_json(data_dir / "stations.json", orient="records", indent=2)

        places = us_geo.copy()
        places[["lat", "lng"]] = places[["lat", "lng"]].round(5)
        places.to_json(data_dir / "places.json", orient="records")

        self.stdout.write(
            self.style.SUCCESS(f"wrote {len(out)} stations and {len(places)} places")
        )