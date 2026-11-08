from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import csv

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "data" / "security-events.xml"
REPORT_DIR = BASE_DIR / "reports"

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

WINDOW = timedelta(minutes=5)
THRESHOLD = 3


def parse_time(value):
    """XML zamanını saat dilimi bilgisiyle okuyup UTC'ye çevir."""
    if not value:
        raise ValueError("Zaman bilgisi boş")

    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if timestamp.tzinfo is None:
        raise ValueError("Saat dilimi bilgisi yok")

    return timestamp.astimezone(timezone.utc)


def busiest_window(timestamps):
    """En fazla olayın bulunduğu 5 dakikalık aralığı bul."""
    ordered = sorted(timestamps)
    left = 0
    best_count = 0
    best_start = None
    best_end = None

    for right, current in enumerate(ordered):
        while current - ordered[left] > WINDOW:
            left += 1

        count = right - left + 1

        if count > best_count:
            best_count = count
            best_start = ordered[left]
            best_end = current

    return best_count, best_start, best_end


def save_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    try:
        root = ET.parse(LOG_FILE).getroot()
    except (OSError, ET.ParseError) as error:
        print(f"XML dosyası okunamadı: {error}")
        return

    if root.tag == f"{{{NS['e']}}}Event":
        events = [root]
    else:
        events = root.findall(".//e:Event", NS)

    if not events:
        print("Windows olay kaydı bulunamadı.")
        return

    counts = Counter()
    failed_users = Counter()
    failure_times = defaultdict(list)
    invalid_times = 0

    for event in events:
        event_id = event.findtext("e:System/e:EventID", namespaces=NS)

        if event_id in ("4624", "4625"):
            counts[event_id] += 1

        if event_id != "4625":
            continue

        fields = {
            item.get("Name"): item.text or ""
            for item in event.findall("e:EventData/e:Data", NS)
        }

        username = (fields.get("TargetUserName") or "").strip().casefold()
        domain = (fields.get("TargetDomainName") or "").strip().upper()

        if username in ("", "-"):
            account = "(bilinmeyen hesap)"
        else:
            account = f"{domain}\\{username}" if domain else username

        failed_users[account] += 1

        time_node = event.find("e:System/e:TimeCreated", NS)
        raw_time = time_node.get("SystemTime") if time_node is not None else None

        try:
            timestamp = parse_time(raw_time)
        except ValueError:
            invalid_times += 1
            continue

        # Bilinmeyen hesapları aynı kullanıcıymış gibi birleştirme.
        if account != "(bilinmeyen hesap)":
            failure_times[account].append(timestamp)

    print(f"Toplam olay: {len(events)}")
    print(f"Başarılı giriş (4624): {counts['4624']}")
    print(f"Başarısız giriş (4625): {counts['4625']}")

    print("\nHesaplara göre başarısız girişler:")
    for account, count in failed_users.most_common():
        print(f"  {account}: {count}")

    alerts = []

    for account, timestamps in sorted(failure_times.items()):
        count, start, end = busiest_window(timestamps)

        if count >= THRESHOLD:
            alerts.append([
                account,
                count,
                start.isoformat(),
                end.isoformat(),
            ])

    print("\nZaman analizi: 5 dakika içinde en az 3 başarısız giriş")
    print("Saatler UTC'dir; Türkiye saati için 3 saat eklenir.")

    if alerts:
        for account, count, start, end in alerts:
            print(f"\nUYARI: {account}")
            print(f"  Giriş sayısı: {count}")
            print(f"  İlk olay: {start}")
            print(f"  Son olay: {end}")
    else:
        print("Eşiği karşılayan bir aralık bulunamadı.")

    if invalid_times:
        print(f"\nZaman analizine alınamayan kayıt: {invalid_times}")

    try:
        REPORT_DIR.mkdir(exist_ok=True)

        save_csv(
            REPORT_DIR / "failed-logins-summary.csv",
            ["Hesap", "Basarisiz Giris Sayisi"],
            failed_users.most_common(),
        )

        save_csv(
            REPORT_DIR / "alerts.csv",
            ["Hesap", "Araliktaki Sayi", "Ilk Olay UTC", "Son Olay UTC"],
            alerts,
        )
    except OSError as error:
        print(f"Rapor kaydedilemedi: {error}")
        return

    print(f"\nRaporlar kaydedildi: {REPORT_DIR}")
    print("Uyarılar inceleme adaylarıdır; tek başına saldırı kanıtı değildir.")


if __name__ == "__main__":
    main()