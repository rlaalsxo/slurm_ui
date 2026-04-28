import datetime


def set_recent_range(start_entry, end_entry, days):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    set_date_range(start_entry, end_entry, start, end)


def set_all_range(start_entry, end_entry):
    set_date_range(start_entry, end_entry, datetime.date(2000, 1, 1), datetime.date.today())


def set_date_range(start_entry, end_entry, start, end):
    start_entry.delete(0, "end")
    start_entry.insert(0, start.isoformat())
    end_entry.delete(0, "end")
    end_entry.insert(0, end.isoformat())


def read_date_range(start_entry, end_entry):
    start_str = start_entry.get().strip()
    end_str = end_entry.get().strip()
    if not start_str or not end_str:
        raise ValueError("Please enter both start and end dates.")

    start = datetime.datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.datetime.strptime(end_str, "%Y-%m-%d") + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()
