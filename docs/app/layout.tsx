import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Layout, Navbar } from "nextra-theme-docs";
import { getPageMap } from "nextra/page-map";
import "nextra-theme-docs/style.css";

const noIndexFollow = process.env.CF_PAGES_BRANCH !== "main";

export const metadata: Metadata = {
    title: {
        default: "Hyperglass Documentation",
        template: "%s | Hyperglass",
    },
    description: "Documentation for Hyperglass, a network looking glass for operators.",
    openGraph: {
        type: "website",
        siteName: "Hyperglass",
    },
    robots: {
        index: !noIndexFollow,
        follow: !noIndexFollow,
    },
};

type RootLayoutProps = Readonly<{ children: ReactNode }>;

export default async function RootLayout({ children }: RootLayoutProps) {
    const pageMap = await getPageMap();

    return (
        <html lang="en" dir="ltr" suppressHydrationWarning>
            <body>
                <Layout
                    docsRepositoryBase="https://github.com/hyperglass-community/hyperglass/tree/main/docs"
                    navbar={
                        <Navbar
                            logo={
                                <picture>
                                    <source media="(prefers-color-scheme: dark)" srcSet="/hyperglass-dark.svg" />
                                    <img src="/hyperglass-light.svg" alt="Hyperglass" height="32" />
                                </picture>
                            }
                            projectLink="https://github.com/hyperglass-community/hyperglass"
                        >
                            <a href="https://github.com/hyperglass-community/hyperglass/wiki">Wiki</a>
                        </Navbar>
                    }
                    pageMap={pageMap}
                >
                    {children}
                </Layout>
            </body>
        </html>
    );
}
