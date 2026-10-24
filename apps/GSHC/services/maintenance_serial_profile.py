"""Expected descriptor parameters and runtime CAPS must agree; never set baud."""


def MaintenanceSerial_Timeout(baudrate, timeout):
    if type(baudrate) is not int or not 1200 <= baudrate <= 2000000:
        return timeout
    return max(timeout, min(30.0, 8210.0 / baudrate + .25))


def MaintenanceSerial_Check(caps, baudrate=None, expected=None):
    if expected is not None:
        if type(expected) is not dict or type(expected.get('baudrate')) is not int:
            raise ValueError('Invalid expected maintenance UART declaration')
        if baudrate != expected['baudrate']:
            raise ValueError(f"Maintenance baud differs from selected descriptor: expected{expected['baudrate']}, selected{baudrate}")
    if 'uart_baud' not in caps:
        if expected is not None:
            raise ValueError('Firmware CAPS do not confirm the descriptor UART; reconnect using matching firmware/description')
        return
    rate = caps['uart_baud']
    if (not isinstance(rate, str) or not rate.isascii() or not rate.isdecimal()
            or len(rate) > 7 or not 1200 <= int(rate) <= 2000000
            or caps.get('uart_format') != '8N1' or caps.get('idle_timeout_ms') != '30000'):
        raise ValueError('Invalid runtime maintenance UART parameters')
    if type(baudrate) is int and int(rate) != baudrate:
        raise ValueError(f'Runtime UART baud{rate} differs from selected{baudrate}; no transfer')
    if expected is not None and (int(rate) != expected['baudrate']
            or str(expected.get('block_size')) != caps.get('max_block')
            or expected.get('block_deadline_ms') != 30000 or expected.get('idle_timeout_ms') != 30000):
        raise ValueError('Runtime CAPS and descriptor transfer parameters differ')
