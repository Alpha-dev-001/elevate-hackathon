import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Elevate — Your store, alive.',
  description: 'Autonomous merchant intelligence. Your store works with you, 24/7.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
