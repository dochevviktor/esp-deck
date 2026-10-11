#pragma once
#include "FreeRTOS.h"
BaseType_t xTaskCreate(void (*task)(void *), const char *name, uint32_t stack,
                      void *argument, UBaseType_t priority, TaskHandle_t *handle);
void xTaskNotifyGive(TaskHandle_t handle);
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait);
