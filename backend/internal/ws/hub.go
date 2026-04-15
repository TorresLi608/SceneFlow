package ws

import "encoding/json"

type BroadcastMessage struct {
	ProjectID string
	Payload   []byte
}

type Hub struct {
	clients    map[string]map[*Client]struct{}
	register   chan *Client
	unregister chan *Client
	broadcast  chan BroadcastMessage
}

func NewHub() *Hub {
	return &Hub{
		clients:    make(map[string]map[*Client]struct{}),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		broadcast:  make(chan BroadcastMessage, 32),
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.register:
			if _, exists := h.clients[client.ProjectID]; !exists {
				h.clients[client.ProjectID] = make(map[*Client]struct{})
			}
			h.clients[client.ProjectID][client] = struct{}{}
		case client := <-h.unregister:
			if projectClients, exists := h.clients[client.ProjectID]; exists {
				if _, ok := projectClients[client]; ok {
					delete(projectClients, client)
					close(client.Send)
				}
				if len(projectClients) == 0 {
					delete(h.clients, client.ProjectID)
				}
			}
		case message := <-h.broadcast:
			projectClients, exists := h.clients[message.ProjectID]
			if !exists {
				continue
			}

			for client := range projectClients {
				select {
				case client.Send <- message.Payload:
				default:
					delete(projectClients, client)
					close(client.Send)
				}
			}
		}
	}
}

func (h *Hub) Register(client *Client) {
	h.register <- client
}

func (h *Hub) Unregister(client *Client) {
	h.unregister <- client
}

func (h *Hub) Publish(projectID string, payload []byte) {
	h.broadcast <- BroadcastMessage{ProjectID: projectID, Payload: payload}
}

func (h *Hub) PublishJSON(projectID string, payload any) error {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	h.Publish(projectID, encoded)
	return nil
}
