from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from api.models import Movement
from api.services.coordinate_encryption import encrypt_coordinates
from api.services.h3_grid import latlng_to_cell


DEFAULT_BATCH_SIZE = 1000


class Command(BaseCommand):
    help = (
        "Backfill H3 cells and encrypted coordinates for existing Movement records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Number of movements to update per batch (default: {DEFAULT_BATCH_SIZE}).",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be a positive integer")

        incomplete_location = (
            Q(h3_cell__isnull=True)
            | Q(h3_cell="")
            | Q(coordinates_encrypted__isnull=True)
            | Q(coordinates_key_version__isnull=True)
        )
        queryset = (
            Movement.objects.filter(incomplete_location)
            .only(
                "id",
                "latitude",
                "longitude",
                "h3_cell",
                "coordinates_encrypted",
                "coordinates_key_version",
            )
            .order_by("pk")
        )

        updated_count = 0
        last_pk = 0

        while True:
            movements = list(queryset.filter(pk__gt=last_pk)[:batch_size])
            if not movements:
                break

            for movement in movements:
                if not movement.h3_cell:
                    movement.h3_cell = latlng_to_cell(
                        movement.latitude,
                        movement.longitude,
                    )

                if (
                    movement.coordinates_encrypted is None
                    or movement.coordinates_key_version is None
                ):
                    encrypted = encrypt_coordinates(
                        movement.latitude,
                        movement.longitude,
                    )
                    movement.coordinates_encrypted = encrypted.ciphertext
                    movement.coordinates_key_version = encrypted.key_version

            with transaction.atomic():
                Movement.objects.bulk_update(
                    movements,
                    [
                        "h3_cell",
                        "coordinates_encrypted",
                        "coordinates_key_version",
                    ],
                    batch_size=batch_size,
                )

            updated_count += len(movements)
            last_pk = movements[-1].pk

        self.stdout.write(
            self.style.SUCCESS(f"Backfilled {updated_count} movement(s).")
        )
