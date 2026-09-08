import { HermesApp } from "@/components/hermes-app";

interface SessionPageProps {
  params: Promise<{ sessionId: string }>;
}

export default async function SessionPage({ params }: SessionPageProps) {
  const { sessionId } = await params;
  return <HermesApp initialSessionId={sessionId} />;
}
