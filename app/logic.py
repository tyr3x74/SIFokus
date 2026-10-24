"""Logika murni: tidak membuka kamera, tidak bergantung pada FPS atau GUI."""

from dataclasses import dataclass
import math
from statistics import median


ALERT_MESSAGE = "Mata tertutup cukup lama. Pertimbangkan jeda istirahat."
MAX_SAMPLE_GAP = 0.5  # Jeda observasi lebih lama memutus kontinuitas.


@dataclass(frozen=True)
class EyeThreshold:
    opened: float
    closed: float
    close_at: float
    reopen_at: float


@dataclass(frozen=True)
class Profile:
    left: EyeThreshold
    right: EyeThreshold


def valid_ears(ears):
    """Batas geometri longgar, bukan ambang mata tertutup."""
    return (
        ears is not None and len(ears) == 2
        and all(math.isfinite(e) and 0 <= e <= 0.7 for e in ears)
    )


def quantile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def fit_eye(open_samples, closed_samples):
    opened, closed = median(open_samples), median(closed_samples)
    gap = opened - closed
    noise = max(
        median(abs(x - opened) for x in open_samples),
        median(abs(x - closed) for x in closed_samples), 0.001,
    )
    # Tolak kondisi terbalik, terlalu berimpit, atau sangat tidak stabil.
    if gap < max(0.012, 0.18 * opened, 3 * noise):
        raise ValueError("Kondisi mata terbuka dan tertutup sulit dibedakan.")
    if quantile(open_samples, 0.2) <= quantile(closed_samples, 0.8) + 0.1 * gap:
        raise ValueError("Sampel mata tumpang tindih atau terlalu bervariasi.")
    return EyeThreshold(opened, closed, closed + 0.4 * gap, closed + 0.6 * gap)


class Calibrator:
    """2 s persiapan, 5 s terbuka, 2 s persiapan, 2 s tertutup."""

    STAGES = (("prepare_open", 2.0), ("open", 5.0),
              ("prepare_closed", 2.0), ("closed", 2.0))

    def __init__(self, now):
        self.index = 0
        self.started = now
        self.profile = None
        self.error = ""
        self.samples = {"open": [], "closed": []}
        self.coverage = {"open": 0.0, "closed": 0.0}
        self.previous_valid = None

    @property
    def stage(self):
        if self.error:
            return "failed"
        if self.profile:
            return "ready"
        return self.STAGES[self.index][0]

    def remaining(self, now):
        if self.stage in ("ready", "failed"):
            return 0.0
        return max(0.0, self.STAGES[self.index][1] - (now - self.started))

    def update(self, now, ears):
        if self.stage in ("ready", "failed"):
            return
        stage, duration = self.STAGES[self.index]
        if now - self.started >= duration:
            # Jangan gunakan frame peralihan atau mengejar fase yang terlewat.
            self.previous_valid = None
            self.index += 1
            self.started = now
            if self.index == len(self.STAGES):
                self._finish()
            return
        if stage not in self.samples:
            return
        if not valid_ears(ears):
            self.previous_valid = None
            return
        self.samples[stage].append(tuple(ears))
        if self.previous_valid is not None:
            dt = now - self.previous_valid
            if 0 < dt <= MAX_SAMPLE_GAP:
                self.coverage[stage] += dt
        self.previous_valid = now

    def _finish(self):
        for stage, seconds, minimum in (("open", 5, 15), ("closed", 2, 8)):
            if (len(self.samples[stage]) < minimum
                    or self.coverage[stage] < seconds * 0.65):
                self.error = "Sampel valid kurang. Hadapkan wajah ke kamera dan kalibrasi ulang."
                return
        try:
            self.profile = Profile(*(
                fit_eye([s[i] for s in self.samples["open"]],
                        [s[i] for s in self.samples["closed"]])
                for i in range(2)
            ))
        except ValueError as exc:
            self.error = f"{exc} Silakan kalibrasi ulang."


@dataclass(frozen=True)
class Detection:
    status: str
    duration: float = 0.0
    warning: bool = False
    event: bool = False
    sound: bool = False
    smoothed: tuple | None = None


class EyeMonitor:
    def __init__(self, profile, trigger_seconds=2.0, cooldown_seconds=8.0):
        self.profile = profile
        self.configure(trigger_seconds, cooldown_seconds)
        self.warning_count = 0
        self.last_sound = -math.inf
        self.armed = False  # Setelah kalibrasi, harus membuka kedua mata dahulu.
        self.reset_tracking()

    def configure(self, trigger_seconds, cooldown_seconds):
        if not (0.5 <= trigger_seconds <= 10 and 2 <= cooldown_seconds <= 60):
            raise ValueError("Durasi pemicu 0,5–10 s; cooldown 2–60 s.")
        self.trigger_seconds = trigger_seconds
        self.cooldown_seconds = cooldown_seconds

    def reset_tracking(self):
        self.last_valid = None
        self.smoothed = None
        self.closed_since = None
        self.is_closed = False
        self.episode_warned = False

    def update(self, ears, now, muted=False):
        if not valid_ears(ears):
            self.reset_tracking()
            return Detection("Tidak valid")
        if self.last_valid is not None and (
            now <= self.last_valid or now - self.last_valid > MAX_SAMPLE_GAP
        ):
            self.reset_tracking()
        if self.smoothed is None:
            self.smoothed = tuple(ears)
        else:
            alpha = 1 - math.exp(-(now - self.last_valid) / 0.07)
            self.smoothed = tuple(a + alpha * (b - a)
                                  for a, b in zip(self.smoothed, ears))
        self.last_valid = now
        thresholds = (self.profile.left, self.profile.right)
        both_open = all(e >= t.reopen_at for e, t in zip(self.smoothed, thresholds))
        any_open = any(e >= t.reopen_at for e, t in zip(self.smoothed, thresholds))
        both_closed = all(e <= t.close_at for e, t in zip(self.smoothed, thresholds))
        if not self.armed:
            self.armed = both_open
            return Detection("Mata terbuka" if self.armed else "Buka kedua mata untuk mulai",
                             smoothed=self.smoothed)
        if any_open:
            self.is_closed = False
            self.closed_since = None
            self.episode_warned = False
        elif both_closed and not self.is_closed:
            self.is_closed = True
            self.closed_since = now
        # Di antara kedua ambang, pertahankan status sebelumnya (hysteresis).
        if not self.is_closed:
            status = "Mata terbuka" if both_open else "Mata transisi / satu mata tertutup"
            return Detection(status, smoothed=self.smoothed)
        duration = now - self.closed_since
        warning = duration >= self.trigger_seconds
        event = warning and not self.episode_warned
        if event:
            self.warning_count += 1
            self.episode_warned = True
        sound = warning and not muted and now - self.last_sound >= self.cooldown_seconds
        if sound:
            self.last_sound = now
        return Detection("Mata tertutup", duration, warning, event, sound, self.smoothed)
