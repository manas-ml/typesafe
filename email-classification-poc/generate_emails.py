#!/usr/bin/env python3
"""
Generate a synthetic dataset of sample emails for the classification POC.

Wipes and regenerates emails/{spam,important,not_spam}/*.txt using a set of
randomized templates per category, so the dataset can be scaled up (e.g. to
500 emails) without hand-authoring each one.

Usage:
    python generate_emails.py [--total 500] [--seed 42]
"""

import argparse
import os
import random
import shutil

from faker import Faker

EMAILS_DIR = os.path.join(os.path.dirname(__file__), "emails")
LABELS = ("spam", "important", "not_spam")

SPOOFED_TLDS = ["biz", "info", "xyz", "top", "click", "cc"]


def spoofed_domain(fake: Faker) -> str:
    brand = random.choice(
        ["paypa1", "amaz0n-support", "usps-redelivery", "apple-id-verify",
         "netflix-billing", "microsoft-alert", "irs-taxrefund", "bank-secure-login"]
    )
    return f"{brand}.{random.choice(SPOOFED_TLDS)}"


# ---------------------------------------------------------------------------
# SPAM templates
# ---------------------------------------------------------------------------

def spam_lottery(fake):
    amount = random.choice([50000, 250000, 500000, 1000000, 2500000])
    return (
        f"claims@{spoofed_domain(fake)}",
        f"You've WON ${amount:,}!! Claim NOW before it expires",
        f"CONGRATULATIONS WINNER!!!\n\n"
        f"Your email address has been randomly selected in our INTERNATIONAL "
        f"LOTTERY DRAW to receive a cash prize of ${amount:,} USD!\n\n"
        f"To claim your winnings, reply with your full name, address, phone "
        f"number, and a copy of your ID. A small processing fee of "
        f"${random.randint(50, 300)} is required to release the funds within "
        f"24 hours.\n\nAct fast! This offer expires in {random.randint(6, 48)} hours.\n\n"
        f"Regards,\nClaims Department",
    )


def spam_phishing_invoice(fake):
    service = random.choice(["PayPal", "Netflix", "Apple", "Amazon", "Chase Bank"])
    amount = round(random.uniform(19.99, 899.99), 2)
    return (
        f"billing@{spoofed_domain(fake)}",
        f"Invoice #{random.randint(10000, 99999)} - Payment Failed, Action Required",
        f"Dear Customer,\n\nWe were unable to process your recent payment of "
        f"${amount} for your {service} subscription. Your account will be "
        f"suspended within 24 hours unless you verify your billing "
        f"information.\n\nClick here to verify your account: "
        f"http://{spoofed_domain(fake)}/login\n\n"
        f"Failure to act will result in permanent account closure.\n\n"
        f"Thank you,\nBilling Support Team",
    )


def spam_tech_support(fake):
    n_viruses = random.randint(2, 9)
    return (
        f"alert@{spoofed_domain(fake)}",
        f"WARNING: Your computer has {n_viruses} viruses detected",
        f"SECURITY ALERT\n\nOur scan has detected {n_viruses} viruses and "
        f"{random.randint(1, 4)} trojans on your device. Your personal files, "
        f"banking information, and passwords are at risk of being stolen.\n\n"
        f"Call our toll-free support line IMMEDIATELY at "
        f"{fake.phone_number()} to speak with a certified technician who "
        f"will remove these threats remotely.\n\nDo not shut down your "
        f"computer before calling, as this may cause permanent data loss.",
    )


def spam_crypto_pump(fake):
    coin = fake.word().capitalize() + "Coin"
    multiplier = random.choice([20, 50, 100, 200])
    return (
        f"signals@{spoofed_domain(fake)}",
        f"\U0001F680 {coin} will do {multiplier}x THIS WEEK - insider info",
        f"Hey,\n\nMy insider contact at a major exchange just tipped me off "
        f"about {coin}, about to get listed on three major platforms "
        f"simultaneously. Early investors in similar plays have seen "
        f"{multiplier}x returns in days.\n\nGet in NOW before the public "
        f"listing announcement.\n\nOnly sharing this with my top "
        f"subscribers. Delete after reading.\n\nNot financial advice ;)",
    )


def spam_weight_loss(fake):
    pounds = random.choice([15, 20, 30, 40])
    days = random.choice([7, 10, 14, 21])
    return (
        f"offers@{spoofed_domain(fake)}",
        f"Lose {pounds} pounds in {days} days with this ONE weird trick",
        f"Doctors HATE her! Local {random.choice(['mom', 'dad', 'nurse'])} "
        f"discovers ancient tribal secret that melts fat overnight with zero "
        f"exercise and zero dieting.\n\nThousands are already seeing results "
        f"in days, not months. Supplies are limited due to overwhelming "
        f"demand.\n\nClaim your free trial bottle (just pay "
        f"${round(random.uniform(1.95, 9.95), 2)} shipping): click here\n\n"
        f"Order in the next 10 minutes to lock in your discount.",
    )


def spam_fake_delivery(fake):
    fee = round(random.uniform(1.5, 4.5), 2)
    return (
        f"notifications@{spoofed_domain(fake)}",
        f"Your package could not be delivered - ${fee} fee required",
        f"DELIVERY NOTICE\n\nWe attempted to deliver your package today but "
        f"a small customs/redelivery fee of ${fee} is required before we can "
        f"complete delivery.\n\nPlease settle this fee within 48 hours or "
        f"your package will be returned to the sender: "
        f"http://{spoofed_domain(fake)}/pay-fee\n\n"
        f"Tracking Number: {fake.bothify(text='#########????######')}",
    )


def spam_romance_scam(fake):
    name = fake.first_name()
    return (
        f"{name.lower()}.lonely@{spoofed_domain(fake)}",
        f"I feel a real connection with you {fake.first_name()}",
        f"Hello dear,\n\nI know we have never met but I saw your profile and "
        f"felt an instant connection. I am currently working overseas as an "
        f"engineer and unfortunately my accounts are frozen.\n\nCould you "
        f"help me with a small transfer of ${random.randint(500, 5000)} so I "
        f"can come visit you? I promise to pay you back as soon as my funds "
        f"are released.\n\nWith love,\n{name}",
    )


def spam_fake_job_offer(fake):
    salary = random.randint(80, 250) * 1000
    return (
        f"hr@{spoofed_domain(fake)}",
        f"You've been selected for a ${salary:,}/year remote position!",
        f"Dear Applicant,\n\nBased on your online profile, you have been "
        f"pre-selected for an exclusive remote position paying ${salary:,} "
        f"per year with no experience required.\n\nTo proceed, please send a "
        f"$99 processing fee for your background check and starter "
        f"equipment kit.\n\nRespond within 24 hours to secure this offer.",
    )


SPAM_TEMPLATES = [
    spam_lottery, spam_phishing_invoice, spam_tech_support, spam_crypto_pump,
    spam_weight_loss, spam_fake_delivery, spam_romance_scam, spam_fake_job_offer,
]


# ---------------------------------------------------------------------------
# NOT_SPAM templates
# ---------------------------------------------------------------------------

def notspam_newsletter(fake):
    pub = fake.catch_phrase().split()[0] + "Weekly"
    return (
        f"newsletter@{fake.domain_name()}",
        f"{pub} #{random.randint(100, 300)}: what's new this month",
        f"Hi there,\n\nHere's your roundup of what's new this month:\n\n"
        f"- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n\n"
        f"Thanks for being a subscriber. You can unsubscribe anytime from "
        f"the link in the footer.\n\nThe {pub} Team",
    )


def notspam_coworker_update(fake):
    name = fake.first_name()
    project = fake.bs().title()
    return (
        f"{name.lower()}.{fake.last_name().lower()}@ourcompany.com",
        f"Weekly status - {project} project",
        f"Hi team,\n\nQuick update on {project} this week:\n\n"
        f"- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n\n"
        f"No blockers right now. Let me know if you have questions before "
        f"next week's sync.\n\nThanks,\n{name}",
    )


def notspam_receipt(fake):
    item = fake.word().capitalize()
    price = round(random.uniform(9.99, 129.99), 2)
    return (
        f"orders@{fake.domain_name()}",
        f"Your order #{random.randint(10000, 99999)} has shipped",
        f"Hi {fake.first_name()},\n\nGood news - your recent order has "
        f"shipped and is on its way!\n\n{item} (x1) - ${price}\n\n"
        f"Estimated delivery: {fake.day_of_week()}, {fake.month_name()} "
        f"{random.randint(1, 28)}.\n\nThanks for shopping with us!",
    )


def notspam_calendar_invite(fake):
    meeting = fake.bs().title()
    return (
        "calendar-noreply@ourcompany.com",
        f"Invitation: {meeting} @ {fake.day_of_week()} {fake.time(pattern='%I:%M %p')}",
        f"You have been invited to the following event:\n\n{meeting}\n"
        f"Where: Conference Room {random.choice('ABC')} / Zoom link in description\n\n"
        f"Agenda:\n- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n\n"
        f"This is a recurring meeting. Please come prepared with updates.",
    )


def notspam_brand_marketing(fake):
    brand = fake.company()
    return (
        f"hello@{fake.domain_name()}",
        f"New arrivals from {brand} are here",
        f"Hi there,\n\nOur latest lineup just dropped! This season we're "
        f"featuring some of our most requested items.\n\nStop by or order "
        f"through the app. As a loyalty member you'll earn double points "
        f"through the end of the month.\n\nSee you soon,\nThe {brand} Team",
    )


def notspam_hr_admin(fake):
    return (
        "hr@ourcompany.com",
        f"Reminder: {fake.bs()} update deadline is {fake.month_name()} {random.randint(1,28)}",
        f"Hi everyone,\n\nJust a friendly reminder that the deadline to "
        f"review and update your info is coming up. No action is needed if "
        f"you'd like to keep your current elections as-is.\n\nYou can make "
        f"changes anytime before the deadline through the portal.\n\nThanks,\nHR Team",
    )


def notspam_meeting_notes(fake):
    return (
        f"{fake.first_name().lower()}@ourcompany.com",
        "Notes from today's sync",
        f"Hi all,\n\nSharing notes from today's meeting:\n\n"
        f"- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n- {fake.catch_phrase()}\n\n"
        f"Let me know if I missed anything.\n\nThanks,\n{fake.first_name()}",
    )


def notspam_survey_request(fake):
    company = fake.company()
    return (
        f"feedback@{fake.domain_name()}",
        f"How was your recent experience with {company}?",
        f"Hi,\n\nWe'd love to hear about your recent experience. The survey "
        f"takes about 2 minutes and helps us improve.\n\nThis is completely "
        f"optional and there's no obligation to respond.\n\nThanks for your "
        f"time,\nThe {company} Team",
    )


NOT_SPAM_TEMPLATES = [
    notspam_newsletter, notspam_coworker_update, notspam_receipt,
    notspam_calendar_invite, notspam_brand_marketing, notspam_hr_admin,
    notspam_meeting_notes, notspam_survey_request,
]


# ---------------------------------------------------------------------------
# IMPORTANT templates
# ---------------------------------------------------------------------------

def important_outage(fake):
    service = fake.word() + "-api"
    pct = random.randint(5, 60)
    return (
        "alerts@pagerduty-monitoring.ourcompany.com",
        f"[SEV-1] {service} returning errors - immediate response needed",
        f"SEVERITY 1 INCIDENT\n\nThe {service} service has been returning "
        f"errors for approximately {pct}% of requests. Error rate is "
        f"climbing.\n\nCurrent impact: customers unable to complete "
        f"purchases.\n\nPlease join the incident bridge immediately and "
        f"acknowledge this page. You are the primary responder for this "
        f"rotation.",
    )


def important_contract_signature(fake):
    vendor = fake.company()
    return (
        f"{fake.first_name().lower()}.{fake.last_name().lower()}@ourcompany.com",
        f"Need your signature on the {vendor} contract by end of day",
        f"Hi,\n\nLegal finalized the contract with {vendor} and we need your "
        f"signature to close it out today - their offer expires at midnight "
        f"if we don't get this back to them.\n\nCan you review and sign by "
        f"5 PM? Happy to hop on a quick call if you have questions before "
        f"signing.\n\nThanks,\n{fake.first_name()}",
    )


def important_security_alert(fake):
    city = fake.city()
    country = fake.country()
    return (
        "security@ourcompany.com",
        "New sign-in to your account from an unrecognized device",
        f"We noticed a new sign-in to your account from a device we don't "
        f"recognize:\n\nLocation: {city}, {country}\nTime: Today at "
        f"{fake.time(pattern='%I:%M %p')}\n\nIf this was you, you can "
        f"disregard this message. If you don't recognize this activity, "
        f"please secure your account immediately by resetting your password.",
    )


def important_client_escalation(fake):
    client = fake.company()
    return (
        f"{fake.first_name().lower()}@{fake.domain_name()}",
        f"URGENT: issue affecting our presentation tomorrow",
        f"Hi team,\n\nWe just discovered a data issue on our end that's "
        f"affecting numbers we present tomorrow morning at "
        f"{client}.\n\nCan someone get on a call with us today to fix this? "
        f"This is a top priority and could affect renewal conversations if "
        f"we can't resolve it in time.\n\nPlease call me directly as soon as "
        f"you see this.\n\n{fake.name()}\nVP Operations, {client}",
    )


def important_deadline(fake):
    thing = random.choice(["lease renewal", "grant application", "permit filing", "RFP response"])
    return (
        "legal@ourcompany.com",
        f"Action required: {thing} deadline is this Friday",
        f"Hi,\n\nThis is a reminder that the {thing} must be submitted by "
        f"this Friday or we lose our current terms.\n\nWe need your "
        f"approval on the attached terms before we can submit. Please "
        f"respond with a go/no-go by end of day tomorrow at the latest.\n\n"
        f"Let me know if you'd like to discuss first.\n\nLegal Team",
    )


def important_family_urgent(fake):
    relative = random.choice(["dad", "mom", "brother", "grandma"])
    return (
        f"{random.choice(['mom', 'dad', 'sis'])}@familymail.com",
        f"Please call me when you get this - it's about {relative}",
        f"Hi honey,\n\nI don't want to worry you but I need you to call me "
        f"as soon as you see this. {relative.capitalize()} had a fall this "
        f"morning and we're at the hospital getting checked out. Stable and "
        f"talking, but doctors want to run some tests.\n\nPlease call when "
        f"you can, even if you're at work.\n\nLove",
    )


def important_overdue_invoice(fake):
    amount = round(random.uniform(2000, 50000), 2)
    days = random.randint(30, 90)
    return (
        f"accounts@{fake.domain_name()}",
        f"OVERDUE: Invoice payment {days} days past due - service suspension notice",
        f"Dear valued customer,\n\nOur records show an outstanding balance "
        f"of ${amount:,.2f} that is now {days} days past due. Continued "
        f"non-payment will result in suspension of services within 5 "
        f"business days.\n\nPlease arrange payment or contact our accounts "
        f"team immediately to avoid disruption.\n\nAccounts Receivable",
    )


def important_legal_notice(fake):
    return (
        "legal@ourcompany.com",
        "Time-sensitive: response required regarding pending litigation matter",
        f"Hi,\n\nOutside counsel needs your input on a discovery request "
        f"related to an active matter. We have a court-imposed deadline of "
        f"{fake.day_of_week()} to respond.\n\nPlease review the attached "
        f"summary and let us know your availability today for a brief "
        f"call.\n\nThanks,\nLegal Team",
    )


IMPORTANT_TEMPLATES = [
    important_outage, important_contract_signature, important_security_alert,
    important_client_escalation, important_deadline, important_family_urgent,
    important_overdue_invoice, important_legal_notice,
]


TEMPLATES_BY_LABEL = {
    "spam": SPAM_TEMPLATES,
    "not_spam": NOT_SPAM_TEMPLATES,
    "important": IMPORTANT_TEMPLATES,
}


def write_email(path: str, from_addr: str, subject: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(f"From: {from_addr}\nSubject: {subject}\n\n{body}\n")


def generate_for_label(label: str, count: int, fake: Faker) -> None:
    out_dir = os.path.join(EMAILS_DIR, label)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    templates = TEMPLATES_BY_LABEL[label]
    for i in range(count):
        template = templates[i % len(templates)]
        from_addr, subject, body = template(fake)
        name = f"{template.__name__}_{i:04d}.txt"
        write_email(os.path.join(out_dir, name), from_addr, subject, body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    per_label = args.total // len(LABELS)
    counts = {label: per_label for label in LABELS}
    counts["spam"] += args.total - per_label * len(LABELS)  # remainder

    for label in LABELS:
        generate_for_label(label, counts[label], fake)
        print(f"Generated {counts[label]} emails in emails/{label}/")

    print(f"Total: {sum(counts.values())} emails")


if __name__ == "__main__":
    main()
