import type { Metadata } from "next";
import { Hanken_Grotesk, Newsreader } from "next/font/google";
import "./globals.css";

// Newsreader is a text serif built for reading on screen; memories are
// sentences, so they are set like entries in a ledger. Hanken Grotesk keeps
// the interface itself plain.
const sans = Hanken_Grotesk({
  variable: "--font-hanken",
  subsets: ["latin"],
});

const serif = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "ContextClock",
  description: "Find out which of an agent's memories have gone out of date.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="min-h-screen bg-paper font-sans text-ink antialiased">
        {children}
      </body>
    </html>
  );
}