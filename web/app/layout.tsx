import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MRMS Hail Swaths",
  description: "Hail exposure swath map viewer",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
