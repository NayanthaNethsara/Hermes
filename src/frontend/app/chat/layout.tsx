export default function ChatLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <main className="bg-background h-screen min-h-0 w-full">{children}</main>
  );
}
