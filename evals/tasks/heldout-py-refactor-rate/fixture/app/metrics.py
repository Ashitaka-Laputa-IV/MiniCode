def success_rate(successes, attempts):
    if attempts == 0:
        return 0.0
    return round(successes / attempts * 100, 1)


def failure_rate(successes, attempts):
    if attempts == 0:
        return 0.0
    return round((attempts - successes) / attempts * 100, 1)
