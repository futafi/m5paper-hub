#include "power.h"

#include "net.h"

#include <M5EPD.h>
#include <Wire.h>
#include <esp_sleep.h>

namespace {
constexpr uint8_t kRtcAddr = 0x51, kControl2 = 0x01, kSeconds = 0x02;
constexpr uint8_t kAlarmFlag = 1 << 3, kTimerFlag = 1 << 2;

bool readRtc(uint8_t reg, uint8_t *dest, uint8_t size) {
    Wire.beginTransmission(kRtcAddr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0 || Wire.requestFrom(kRtcAddr, size) != size) return false;
    for (int i = 0; i < size; ++i) dest[i] = Wire.read();
    return true;
}

int bcd(uint8_t value) {
    return (value & 0x0f) > 9 ? -1 : (value >> 4) * 10 + (value & 0x0f);
}
}  // namespace

bool scheduledWake() {
    // GT911 has already started Wire on GPIO21/22, but RTC.begin() has NOT
    // run yet: it writes 0 to Control/Status 2, including AF and TF.
    uint8_t status = 0;
    const bool read = readRtc(kControl2, &status, 1);
    const bool espTimer = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER;
    Serial.printf("Wake: RTC status=%02x read=%d, AF=%d TF=%d ESP timer=%d\n",
                  status, read, bool(status & kAlarmFlag), bool(status & kTimerFlag), espTimer);
    // shutdown(seconds) enables TIE (countdown timer), which latches TF, not AF.
    return espTimer || (read && (status & (kAlarmFlag | kTimerFlag)));
}

void setClock(uint8_t hour, uint8_t minute, uint8_t second) {
    if (hour > 23 || minute > 59 || second > 59) return;
    rtc_time_t rtc{};
    rtc.hour = hour;
    rtc.min = minute;
    rtc.sec = second;
    M5.RTC.setTime(&rtc);
}

void clockText(char (&time)[6]) {
    strlcpy(time, "--:--", sizeof time);
    uint8_t clock[3];
    if (!readRtc(kSeconds, clock, sizeof clock) || (clock[0] & 0x80)) return;
    const int hr = bcd(clock[2] & 0x3f), min = bcd(clock[1] & 0x7f);
    if (hr >= 0 && hr < 24 && min >= 0 && min < 60) snprintf(time, sizeof time, "%02d:%02d", hr, min);
}

[[noreturn]] void sleepFor(uint32_t seconds) {
    // BM8563 countdown is 8-bit, with a minute prescaler above 255 s.
    seconds = constrain(seconds, 1U, 255U * 60U);
    stopWiFi();
    Serial.printf("Sleeping %lu s\n", static_cast<unsigned long>(seconds));
    Serial.flush();
    M5.shutdown(seconds);
    delay(100);  // Reaching this point usually means USB is supplying power.
    esp_sleep_enable_timer_wakeup(seconds * 1000000ULL);
    esp_deep_sleep_start();
    __builtin_unreachable();
}
