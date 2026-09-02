TARGET_MCU        := SIMULATOR
TARGET_MCU_FAMILY := SITL
SIMULATOR_BUILD    = yes

TARGET_SRC = \
            drivers/accgyro/accgyro_virtual.c \
            drivers/barometer/barometer_virtual.c \
            drivers/compass/compass_virtual.c \
            drivers/serial_tcp.c \
            io/gps_virtual.c \
            blackbox/blackbox_virtual.c

ifeq ($(AEROLINK_SITL),1)
TARGET_FLAGS += -DUSE_AEROLINK
TARGET_SRC += io/aerolink.c io/aerolink_sitl.c
endif

SIZE_OPTIMISED_SRC += \
            drivers/serial_tcp.c
