"""Keeps a person's contact record and portal sign-in in step.

A person is one row on the employer's contact list; if they can sign in, an ``EmployerMember`` is
linked to that row. Whoever edits the contact (PI staff, or the company on its own profile), the
member's name and job title follow it, and the contact's e-mail stays the sign-in name: changing
where invitations and password resets go is not a contact edit, so the e-mail is put back.
"""

from apps.employers import services as employers

from .models import EmployerMember


def follow_contact(sender, contact, **kwargs):
    member = EmployerMember.objects.select_related("user").filter(contact_id=contact.pk).first()
    if member is None:
        return
    if (member.full_name, member.job_title) != (contact.name, contact.role):
        member.full_name, member.job_title = contact.name, contact.role
        member.save(update_fields=["full_name", "job_title"])
    if contact.email != member.user.email:
        employers.set_contact_email(contact, member.user.email)


def connect():
    employers.contact_saved.connect(follow_contact, dispatch_uid="portal.follow_contact")
