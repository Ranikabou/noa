import './globals.css';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0f0f12] text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
