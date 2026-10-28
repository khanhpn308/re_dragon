package tcp

import (
	"context"
	"crypto/rand"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"sync"
	"time"

	"returnsaiyan/gameserver/internal/protocol"
)

var (
	ErrConnectionClosed = errors.New("connection closed")
	ErrWriteBufferFull  = errors.New("outbound write buffer full")
)

type PacketHandler interface {
	HandlePacket(conn *ClientConn, pkt *protocol.Packet) error
}

// ClientConn wraps a single client connection.
type ClientConn struct {
	id     string
	conn   net.Conn
	seed   uint32
	key    byte
	logger *slog.Logger

	decoder *protocol.C2SStreamDecoder
	handler PacketHandler

	writeCh chan []byte
	ctx     context.Context
	cancel  context.CancelFunc
	wg      sync.WaitGroup

	readTimeout  time.Duration
	writeTimeout time.Duration

	closed   bool
	closeMtx sync.Mutex
}

func NewClientConn(
	id string,
	rawConn net.Conn,
	handler PacketHandler,
	readTimeout time.Duration,
	writeTimeout time.Duration,
	logger *slog.Logger,
) (*ClientConn, error) {
	// Generate random 32-bit seed
	var seedBuf [4]byte
	if _, err := rand.Read(seedBuf[:]); err != nil {
		return nil, fmt.Errorf("failed to generate crypto seed: %w", err)
	}
	seed := binary.BigEndian.Uint32(seedBuf[:])
	key := protocol.GerarChaveSecreta(seed)

	ctx, cancel := context.WithCancel(context.Background())

	c := &ClientConn{
		id:           id,
		conn:         rawConn,
		seed:         seed,
		key:          key,
		logger:       logger.With(slog.String("conn_id", id), slog.String("remote_addr", rawConn.RemoteAddr().String())),
		decoder:      protocol.NewC2SStreamDecoder(key),
		handler:      handler,
		writeCh:      make(chan []byte, 64),
		ctx:          ctx,
		cancel:       cancel,
		readTimeout:  readTimeout,
		writeTimeout: writeTimeout,
	}

	return c, nil
}

func (c *ClientConn) ID() string {
	return c.id
}

func (c *ClientConn) Context() context.Context {
	return c.ctx
}

func (c *ClientConn) Key() byte {
	return c.key
}

func (c *ClientConn) Seed() uint32 {
	return c.seed
}

// Start initiates the greeting transmission and reader/writer goroutines.
func (c *ClientConn) Start() error {
	// 1. Send the initial 7-byte handshake greeting to the client
	greeting := protocol.BuildServerGreeting(c.seed)
	if err := c.conn.SetWriteDeadline(time.Now().Add(c.writeTimeout)); err != nil {
		return fmt.Errorf("failed to set write deadline for greeting: %w", err)
	}
	if _, err := c.conn.Write(greeting); err != nil {
		return fmt.Errorf("failed to send handshake greeting: %w", err)
	}

	c.logger.Info("handshake greeting sent", slog.String("seed", fmt.Sprintf("0x%08X", c.seed)), slog.String("key", fmt.Sprintf("0x%02X", c.key)))

	// 2. Launch background reader and writer
	c.wg.Add(2)
	go c.writeLoop()
	go c.readLoop()

	return nil
}

func (c *ClientConn) readLoop() {
	defer c.wg.Done()
	defer c.Close()

	buf := make([]byte, 4096)
	for {
		select {
		case <-c.ctx.Done():
			return
		default:
		}

		if c.readTimeout > 0 {
			_ = c.conn.SetReadDeadline(time.Now().Add(c.readTimeout))
		}

		n, err := c.conn.Read(buf)
		if err != nil {
			if !errors.Is(err, io.EOF) && !errors.Is(err, net.ErrClosed) {
				c.logger.Debug("read error", slog.String("error", err.Error()))
			}
			return
		}

		if n > 0 {
			c.logger.Info("raw bytes received",
				slog.String("conn_id", c.id),
				slog.Int("bytes", n),
				slog.String("hex", fmt.Sprintf("%x", buf[:n])),
			)
			packets, err := c.decoder.Feed(buf[:n])
			if err != nil {
				c.logger.Warn("stream decode error, closing connection", slog.String("error", err.Error()))
				return
			}

			for _, pkt := range packets {
				c.logger.Info("packet received", slog.String("conn_id", c.id), slog.String("opcode", fmt.Sprintf("0x%02X", pkt.Opcode)), slog.Int("len", len(pkt.Body)))
				if c.handler != nil {
					if err := c.handler.HandlePacket(c, pkt); err != nil {
						c.logger.Warn("packet handler error", slog.String("opcode", fmt.Sprintf("0x%02X", pkt.Opcode)), slog.String("error", err.Error()))
					}
				}
			}
		}
	}
}

func (c *ClientConn) writeLoop() {
	defer c.wg.Done()
	defer c.Close()

	for {
		select {
		case <-c.ctx.Done():
			return
		case msg, ok := <-c.writeCh:
			if !ok {
				return
			}
			if c.writeTimeout > 0 {
				_ = c.conn.SetWriteDeadline(time.Now().Add(c.writeTimeout))
			}
			if _, err := c.conn.Write(msg); err != nil {
				c.logger.Debug("write error", slog.String("error", err.Error()))
				return
			}
		}
	}
}

// SendPacket encrypts an S2C packet using independent XOR and queues it for transmission.
func (c *ClientConn) SendPacket(pw *protocol.PacketWriter) error {
	c.closeMtx.Lock()
	if c.closed {
		c.closeMtx.Unlock()
		return ErrConnectionClosed
	}
	c.closeMtx.Unlock()

	encFrame, err := pw.FinalizeS2C(c.key)
	if err != nil {
		return err
	}

	select {
	case c.writeCh <- encFrame:
		return nil
	case <-c.ctx.Done():
		return ErrConnectionClosed
	default:
		return ErrWriteBufferFull
	}
}

// Close gracefully closes the client connection.
func (c *ClientConn) Close() error {
	c.closeMtx.Lock()
	if c.closed {
		c.closeMtx.Unlock()
		return nil
	}
	c.closed = true
	c.closeMtx.Unlock()

	c.cancel()
	err := c.conn.Close()
	c.wg.Wait()
	return err
}
