"""Write synthetic resume PDFs for the demo (SPEC §10, PLAN Phase 4).

The Kaggle resumes carry no names or contact details, so these fictional people
let the demo show blind mode and reveal. Every person here is invented: emails use
example.com, phone numbers use the 555-01xx range reserved for fiction, and each
PDF says it is synthetic. Some deliberately include things the pipeline must
strip (third-person pronouns, a title, date of birth, gender, marital status).

Usage, from backend/:  python scripts/make_synthetic_resumes.py  [--out eval/synthetic]
Needs no extra packages: it writes simple text PDFs directly.
"""

import argparse
from pathlib import Path

# ---- a minimal text-only PDF writer ------------------------------------------------

PAGE_W, PAGE_H, MARGIN = 612, 792, 54  # US Letter, points
FONTS = {"regular": "F1", "bold": "F2"}


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")  # WinAnsiEncoding
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _wrap(text: str, size: float, width: float) -> list[str]:
    max_chars = max(20, int(width / (size * 0.5)))  # Helvetica averages about 0.5 em per character
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def build_pdf(blocks: list[tuple[str, float, str, float]]) -> bytes:
    """blocks: (text, font size, "regular"|"bold", space before). Returns PDF bytes."""
    pages: list[list[bytes]] = [[]]
    y = PAGE_H - MARGIN
    for text, size, weight, before in blocks:
        indent = 9 if text.startswith("• ") else 0
        wrapped = _wrap(text, size, PAGE_W - 2 * MARGIN - indent) or [""]
        y -= before
        for i, line in enumerate(wrapped):
            if y - size < MARGIN:
                pages.append([])
                y = PAGE_H - MARGIN
            y -= size * 1.35
            x = MARGIN + (9 if indent and i else 0)  # hanging indent for wrapped bullet lines
            pages[-1].append(b"BT /%s %.1f Tf %.1f %.1f Td (%s) Tj ET" % (FONTS[weight].encode(), size, x, y, _escape(line)))

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    catalog = add(b"")  # filled in below
    pages_obj = add(b"")
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kids = []
    for content in pages:
        stream = b"\n".join(content)
        c = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>" % (pages_obj, PAGE_W, PAGE_H, c, f1, f2)
        ))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
    objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def resume_blocks(r: dict) -> list[tuple[str, float, str, float]]:
    blocks = [(r["name"], 20, "bold", 0), (r["contact"], 9.5, "regular", 2)]
    for title, items in r["sections"]:
        blocks.append((title.upper(), 11, "bold", 14))
        for item in items:
            if isinstance(item, tuple):  # (heading, detail lines)
                blocks.append((item[0], 10.5, "bold", 6))
                blocks += [(line, 10, "regular", 1) for line in item[1]]
            else:
                blocks.append((item, 10, "regular", 2))
    blocks.append(("Synthetic resume created for the FairScreen demo. This person is fictional.", 8, "regular", 18))
    return blocks


# ---- the fictional people --------------------------------------------------------------

RESUMES = {
    "aisha_mensah": {
        "name": "Aisha Mensah",
        "contact": "aisha.mensah@example.com | +1 (404) 555-0134 | linkedin.com/in/aisha-mensah-synthetic | Atlanta, GA 30318",
        "sections": [
            ("Profile", ["Aisha Mensah is a systems administrator with seven years of experience running Windows "
                         "infrastructure for healthcare and logistics organisations. She is known for calm incident "
                         "handling and for automating routine work with PowerShell."]),
            ("Experience", [
                ("Senior Systems Administrator - Peachtree Regional Health, Atlanta, GA (Mar 2021 - Present)", [
                    "• Administers 140 Windows Server 2019/2022 hosts and Active Directory for 2,300 users across 6 sites.",
                    "• Led the migration of 85 workloads from ageing Hyper-V hosts to a VMware vSphere 8 cluster with zero unplanned downtime.",
                    "• Designed Group Policy baselines and LAPS rollout that closed 40 audit findings.",
                    "• Escalation point for a 7-person service desk; wrote the runbooks the team uses for tier-2 issues.",
                ]),
                ("Systems Administrator - Southline Freight, Marietta, GA (Jun 2017 - Feb 2021)", [
                    "• Ran DNS, DHCP, VLANs and site-to-site VPNs for 3 warehouses and 400 users.",
                    "• Moved email to Exchange Online and rolled out Microsoft Teams to 400 staff.",
                    "• Automated onboarding and offboarding with PowerShell, cutting account setup from 2 hours to 10 minutes.",
                ]),
            ]),
            ("Education", ["B.S. Information Technology, Kennesaw Valley University - 2013-2017, GPA 3.7/4.0"]),
            ("Skills", ["Windows Server, Active Directory, Group Policy, VMware vSphere, Hyper-V, PowerShell, Microsoft 365, "
                        "Exchange Online, Azure AD Connect, Veeam Backup, DNS, DHCP, VLANs, Fortinet firewalls, ServiceNow"]),
            ("Certifications", ["CompTIA Security+ (2019)", "Microsoft Certified: Azure Administrator Associate (2023)", "ITIL 4 Foundation (2022)"]),
        ],
    },
    "daniel_kowalski": {
        "name": "Mr. Daniel Kowalski",
        "contact": "d.kowalski@example.com | (312) 555-0187 | github.com/dkowalski-synthetic | Chicago, Illinois",
        "sections": [
            ("Summary", ["Network engineer with 4 years of experience in campus and branch networking. Mr. Kowalski holds a "
                         "CCNA and has supported Windows desktops and servers, but his virtualization experience is limited "
                         "to a lab environment."]),
            ("Experience", [
                ("Network Engineer - Lakeshore Credit Union, Chicago, IL (Aug 2022 - Present)", [
                    "• Maintains Cisco Catalyst switching, VLANs and OSPF routing for 22 branches.",
                    "• Replaced the branch VPN mesh with SD-WAN, improving uptime to 99.97%.",
                    "• Handles tier-2 desktop and Windows Server tickets when the service desk escalates.",
                ]),
                ("IT Support Technician - Midway Community College, Chicago, IL (Jan 2021 - Jul 2022)", [
                    "• Supported 600 staff and students with hardware, software and Wi-Fi issues.",
                    "• Reset accounts and managed security groups in Active Directory.",
                ]),
            ]),
            ("Education", ["B.S. Computer Networking, Great Lakes Institute of Technology - 2016-2020"]),
            ("Skills", ["Cisco IOS, VLANs, OSPF, BGP basics, SD-WAN, Wireshark, Windows 10/11, Active Directory, Python for network automation"]),
            ("Certifications", ["Cisco CCNA (2021)", "CompTIA Network+ (2020)"]),
            ("Projects", [("Home virtualization lab", ["Built a Proxmox lab with a pfSense firewall and a Windows Server domain to practise server administration."])]),
        ],
    },
    "rohan_deshpande": {
        "name": "Rohan Deshpande",
        "contact": "rohan.deshpande@example.com | +1 (512) 555-0119 | Flat 12, Shanti Apartments, Kothrud, Pune 411038, India",
        "sections": [
            ("Career Objective", ["To work as a systems administrator where I can use my experience in Windows and Linux "
                                  "server management and grow with the organisation."]),
            ("Experience", [
                ("System Administrator - Sahyadri Software Services, Pune (Jul 2019 - Present)", [
                    "• Manage 60 Windows and RHEL servers for client projects; patching, backups and monitoring with Zabbix.",
                    "• Administer Active Directory, DNS and DHCP for 450 employees.",
                    "• Maintain the VMware ESXi environment (12 hosts) and perform quarterly DR tests.",
                    "• Support end users for laptop, Outlook and VPN issues as part of the IT helpdesk rotation.",
                ]),
            ]),
            ("Education", [
                "B.E. Computer Engineering, Deccan College of Engineering, Pune - 2015-2019, 7.9/10 CGPA",
                "HSC (Class XII), Maharashtra State Board - 2015, 84%",
            ]),
            ("Technical Skills", ["Windows Server 2016/2019, Active Directory, RHEL 8, Bash, PowerShell basics, VMware ESXi, "
                                  "Veeam, Zabbix, TCP/IP, DNS, DHCP, Microsoft 365 administration"]),
            ("Certifications", ["Red Hat Certified System Administrator (RHCSA)", "Microsoft Certified: Azure Fundamentals (AZ-900)"]),
            ("Personal Details", [
                "Date of Birth: 14/02/1997",
                "Gender: Male",
                "Marital Status: Single",
                "Nationality: Indian",
                "Languages: English, Hindi, Marathi",
            ]),
        ],
    },
    "mei_lin_zhou": {
        "name": "Mei Lin Zhou",
        "contact": "meilin.zhou@example.com | 415-555-0162 | linkedin.com/in/meilin-zhou-synthetic | Oakland, CA",
        "sections": [
            ("Summary", ["IT support technician with two years of help-desk experience and a strong home lab. She is "
                         "looking for her first systems administration role and is studying for the Microsoft "
                         "Azure Administrator exam."]),
            ("Experience", [
                ("IT Support Technician - Bayview Public Library, Oakland, CA (Sep 2023 - Present)", [
                    "• First-line support for 180 staff and 90 public computers across 4 branches.",
                    "• Images and deploys Windows 11 laptops with Microsoft Intune; unlocks accounts in Active Directory.",
                    "• Documents fixes in the Freshservice knowledge base; resolved 1,400 tickets in 2025.",
                ]),
            ]),
            ("Education", ["B.S. Information Systems, Pacific Coast State University - 2019-2023, GPA 3.4"]),
            ("Skills", ["Windows 11, Microsoft Intune, Active Directory, Microsoft 365, Freshservice, basic PowerShell, Hyper-V (lab), networking basics"]),
            ("Certifications", ["CompTIA A+ (2023)"]),
            ("Projects", [("Home lab", ["Hyper-V host running a Windows Server 2022 domain controller, DHCP and a file server; practises Group Policy and backups."])]),
        ],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "eval" / "synthetic"))
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for slug, resume in RESUMES.items():
        path = out / f"synthetic_{slug}.pdf"
        path.write_bytes(build_pdf(resume_blocks(resume)))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
