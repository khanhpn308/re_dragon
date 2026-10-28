#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define PACKET_MAGIC 0x5352 /* "RS" in hex */

typedef struct {
    uint16_t magic;
    uint8_t opcode;
    uint8_t flags;
    uint16_t length;
    uint16_t checksum;
} __attribute__((packed)) PacketHeader;

uint16_t calculate_checksum(const uint8_t *data, size_t len) {
    uint32_t sum = 0;
    for (size_t i = 0; i < len; ++i) {
        sum = (sum + data[i]) ^ (data[i] << 1);
    }
    return (uint16_t)(sum & 0xFFFF);
}

int validate_header(const uint8_t *buffer, size_t size) {
    if (size < sizeof(PacketHeader)) {
        return -1;
    }
    const PacketHeader *hdr = (const PacketHeader *)buffer;
    if (hdr->magic != PACKET_MAGIC) {
        return -2;
    }
    if (hdr->length > 1024) {
        return -3;
    }
    return 0;
}

int process_packet(const uint8_t *buffer, size_t size) {
    int vres = validate_header(buffer, size);
    if (vres != 0) {
        return vres;
    }
    const PacketHeader *hdr = (const PacketHeader *)buffer;
    uint16_t expected_cs = hdr->checksum;
    
    /* Checksum calculated over payload */
    const uint8_t *payload = buffer + sizeof(PacketHeader);
    size_t payload_len = size - sizeof(PacketHeader);
    uint16_t actual_cs = calculate_checksum(payload, payload_len);
    
    if (expected_cs != actual_cs) {
        return -4;
    }
    return (int)hdr->opcode;
}

int main(int argc, char **argv) {
    uint8_t sample[sizeof(PacketHeader) + 4] = {
        0x52, 0x53, /* magic RS */
        0x10,       /* opcode 0x10 */
        0x01,       /* flags */
        0x04, 0x00, /* length = 4 */
        0x00, 0x00, /* checksum placeholder */
        0xDE, 0xAD, 0xBE, 0xEF /* payload */
    };
    PacketHeader *hdr = (PacketHeader *)sample;
    hdr->checksum = calculate_checksum(sample + sizeof(PacketHeader), 4);
    
    int result = process_packet(sample, sizeof(sample));
    printf("Processed packet opcode: 0x%02X\n", result);
    return (result == 0x10) ? 0 : 1;
}
