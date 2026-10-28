package tcp

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"sync"
	"sync/atomic"
	"time"
)

type Config struct {
	Addr           string
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	MaxConnections int
}

func DefaultConfig() Config {
	return Config{
		Addr:           "127.0.0.1:30001",
		ReadTimeout:    30 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 5000,
	}
}

type Server struct {
	cfg     Config
	handler PacketHandler
	logger  *slog.Logger

	listener net.Listener
	conns    map[string]*ClientConn
	connsMtx sync.RWMutex
	connSeq  atomic.Uint64

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup

	running atomic.Bool
}

func NewServer(cfg Config, handler PacketHandler, logger *slog.Logger) *Server {
	if cfg.MaxConnections <= 0 {
		cfg.MaxConnections = 5000
	}
	if cfg.ReadTimeout <= 0 {
		cfg.ReadTimeout = 30 * time.Second
	}
	if cfg.WriteTimeout <= 0 {
		cfg.WriteTimeout = 5 * time.Second
	}
	if logger == nil {
		logger = slog.Default()
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &Server{
		cfg:     cfg,
		handler: handler,
		logger:  logger,
		conns:   make(map[string]*ClientConn),
		ctx:     ctx,
		cancel:  cancel,
	}
}

func (s *Server) Start() error {
	l, err := net.Listen("tcp", s.cfg.Addr)
	if err != nil {
		return fmt.Errorf("failed to bind TCP listener on %s: %w", s.cfg.Addr, err)
	}
	s.listener = l
	s.running.Store(true)
	s.logger.Info("TCP Game Server started", slog.String("addr", l.Addr().String()))

	s.wg.Add(1)
	go s.acceptLoop()

	return nil
}

func (s *Server) Addr() net.Addr {
	if s.listener != nil {
		return s.listener.Addr()
	}
	return nil
}

func (s *Server) ActiveConnections() int {
	s.connsMtx.RLock()
	defer s.connsMtx.RUnlock()
	return len(s.conns)
}

func (s *Server) acceptLoop() {
	defer s.wg.Done()

	for {
		rawConn, err := s.listener.Accept()
		if err != nil {
			select {
			case <-s.ctx.Done():
				return
			default:
				if errors.Is(err, net.ErrClosed) {
					return
				}
				s.logger.Warn("accept error", slog.String("error", err.Error()))
				continue
			}
		}

		// Enforce MaxConnections limit
		if s.ActiveConnections() >= s.cfg.MaxConnections {
			s.logger.Warn("max connections reached, rejecting client", slog.String("remote_addr", rawConn.RemoteAddr().String()))
			_ = rawConn.Close()
			continue
		}

		connID := fmt.Sprintf("conn-%d", s.connSeq.Add(1))
		s.logger.Info("client connection accepted", slog.String("conn_id", connID), slog.String("remote_addr", rawConn.RemoteAddr().String()))
		clientConn, err := NewClientConn(
			connID,
			rawConn,
			s.handler,
			s.cfg.ReadTimeout,
			s.cfg.WriteTimeout,
			s.logger,
		)
		if err != nil {
			s.logger.Error("failed to create client connection", slog.String("error", err.Error()))
			_ = rawConn.Close()
			continue
		}

		s.registerConn(clientConn)

		go func(c *ClientConn) {
			if err := c.Start(); err != nil {
				s.logger.Warn("failed to start client conn", slog.String("error", err.Error()))
				s.unregisterConn(c.ID())
				return
			}
			<-c.Context().Done()
			s.unregisterConn(c.ID())
		}(clientConn)
	}
}

// GetConn retrieves an active connection by ID.
func (s *Server) GetConn(connID string) (*ClientConn, bool) {
	s.connsMtx.RLock()
	defer s.connsMtx.RUnlock()
	c, ok := s.conns[connID]
	return c, ok
}

func (s *Server) registerConn(c *ClientConn) {
	s.connsMtx.Lock()
	defer s.connsMtx.Unlock()
	s.conns[c.ID()] = c
}

func (s *Server) unregisterConn(id string) {
	s.connsMtx.Lock()
	defer s.connsMtx.Unlock()
	delete(s.conns, id)
}

func (s *Server) Stop(timeout time.Duration) error {
	if !s.running.CompareAndSwap(true, false) {
		return nil
	}

	s.logger.Info("shutting down TCP Game Server...")
	s.cancel()

	var closeErr error
	if s.listener != nil {
		closeErr = s.listener.Close()
	}

	// Close all active connections
	s.connsMtx.Lock()
	for _, c := range s.conns {
		_ = c.Close()
	}
	s.conns = make(map[string]*ClientConn)
	s.connsMtx.Unlock()

	done := make(chan struct{})
	go func() {
		s.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		s.logger.Info("TCP Game Server stopped gracefully")
		return closeErr
	case <-time.After(timeout):
		s.logger.Warn("TCP Game Server shutdown timed out")
		return errors.New("server shutdown timed out")
	}
}
