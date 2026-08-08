// The /chat archive route: the full-page view of the same conversation the
// persistent left panel shows. State is shared via ChatContext, so switching
// between the two never loses history or an in-flight generation.
import { ChatSurface } from "../components/ChatSurface";

export function ChatPage() {
  return <ChatSurface />;
}
