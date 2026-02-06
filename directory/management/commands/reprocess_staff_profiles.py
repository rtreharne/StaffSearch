import time

from django.core.management.base import BaseCommand

from directory.crawler import extract_staff_fields, extract_text_content
from directory.models import Department, Faculty, Institute, StaffProfile
from directory.utils import hash_text


class Command(BaseCommand):
    help = "Reprocess staff profiles from stored raw_html to update extracted fields."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit the number of profiles processed (0 = no limit).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing to the database.",
        )
        parser.add_argument(
            "--reembed",
            action="store_true",
            help="Queue re-embedding for updated profiles.",
        )

    def handle(self, *args, **options):
        limit = options["limit"] or 0
        dry_run = options["dry_run"]
        reembed = options["reembed"]

        qs = StaffProfile.objects.order_by("id")
        if limit:
            qs = qs[:limit]

        total = 0
        updated = 0
        skipped = 0
        embeds = 0
        started_at = time.time()
        total_count = qs.count()
        last_log = started_at

        for staff in qs.iterator(chunk_size=200):
            total += 1
            if not staff.raw_html:
                skipped += 1
                continue

            fields = extract_staff_fields(staff.raw_html, base_url=staff.profile_url)
            new_text_content = extract_text_content(staff.raw_html)
            new_content_hash = hash_text(new_text_content)

            faculty_name = (fields.get("faculty", "") or "").strip()
            institute_name = (fields.get("institute", "") or "").strip()
            department_name = (fields.get("department", "") or "").strip()

            faculty = None
            institute = None
            department = None

            if faculty_name:
                faculty, _ = Faculty.objects.get_or_create(name=faculty_name)
            if institute_name:
                institute, _ = Institute.objects.get_or_create(
                    name=institute_name,
                    defaults={"faculty": faculty},
                )
                if faculty and institute.faculty_id != faculty.id:
                    institute.faculty = faculty
                    institute.save(update_fields=["faculty"])
            if department_name:
                department, _ = Department.objects.get_or_create(
                    name=department_name,
                    defaults={"institute": institute},
                )
                if institute and department.institute_id != institute.id:
                    department.institute = institute
                    department.save(update_fields=["institute"])

            update_fields = []

            if staff.name != fields.get("name", ""):
                staff.name = fields.get("name", "")
                update_fields.append("name")
            if staff.title != fields.get("title", ""):
                staff.title = fields.get("title", "")
                update_fields.append("title")
            if staff.suffix != fields.get("suffix", ""):
                staff.suffix = fields.get("suffix", "")
                update_fields.append("suffix")

            if staff.faculty_id != (faculty.id if faculty else None):
                staff.faculty = faculty
                update_fields.append("faculty")
            if staff.institute_id != (institute.id if institute else None):
                staff.institute = institute
                update_fields.append("institute")
            if staff.department_id != (department.id if department else None):
                staff.department = department
                update_fields.append("department")

            if staff.faculty_text != faculty_name:
                staff.faculty_text = faculty_name
                update_fields.append("faculty_text")
            if staff.institute_text != institute_name:
                staff.institute_text = institute_name
                update_fields.append("institute_text")
            if staff.department_text != department_name:
                staff.department_text = department_name
                update_fields.append("department_text")

            if staff.text_content != new_text_content:
                staff.text_content = new_text_content
                update_fields.append("text_content")
            if staff.content_hash != new_content_hash:
                staff.content_hash = new_content_hash
                update_fields.append("content_hash")

            if not update_fields:
                pass
            else:
                updated += 1

                if not dry_run:
                    staff.save(update_fields=update_fields)
                    if reembed:
                        from directory.tasks import embed_staff_profile

                        embed_staff_profile.delay(staff.id)
                        embeds += 1

            now = time.time()
            if now - last_log >= 5:
                rate = total / max(now - started_at, 0.001)
                remaining = max(total_count - total, 0)
                eta_seconds = remaining / max(rate, 0.001)
                self.stdout.write(
                    "Progress: {}/{} | Updated: {} | Skipped: {} | Rate: {:.1f}/s | ETA: {:.1f}s".format(
                        total, total_count, updated, skipped, rate, eta_seconds
                    )
                )
                last_log = now

        elapsed = time.time() - started_at
        rate = total / max(elapsed, 0.001)
        self.stdout.write(
            "Processed: {} | Updated: {} | Skipped (no raw_html): {} | Embeds queued: {} | Time: {:.1f}s | Rate: {:.1f}/s".format(
                total, updated, skipped, embeds, elapsed, rate
            )
        )
