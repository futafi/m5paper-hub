#pragma once

#include <stdint.h>

// True if the RTC alarm (battery) or the ESP32 timer (USB) woke the board,
// false if a person did. Call before M5.RTC.begin().
bool scheduledWake();
void setClock(uint8_t hour, uint8_t minute, uint8_t second);
void clockText(char (&time)[6]);
[[noreturn]] void sleepFor(uint32_t seconds);
