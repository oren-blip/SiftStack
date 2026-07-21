# Troubleshooting Guide

Common issues and solutions for Sift sequences, drip campaigns, tasks, presets, and general operations.

## Sequence Issues

### Sequence Won't Save
- Verify at least one **trigger** AND one **action** exist
- Ensure sequence has a **name**
- Check that you selected a **folder**

### Sequence Triggered But Didn't Run
- Large batch triggers may take a few minutes to process
- Check if other actions are running simultaneously
- Verify the sequence is **toggled ON**

### Sequence Didn't Run on Upload
- **Tag/List triggers only work for manual additions**, not uploads
- Use **Property Status Change** trigger for upload-based automations

### Sequence Loop Error
- Sequences **cannot trigger other sequences**
- Combine related automations into a **single sequence**

### Card Not Moving/Adding to Board
- Card may **already exist** on target board (action skips duplicates)
- Verify card is on the expected source board/phase
- Check that board and phase names match **exactly** in the condition

### Wrong Team Member Assigned
- Check if **round-robin** is configured correctly
- Verify the **assignee selection** in the sequence action
- Ensure the property record is also assigned to restricted roles

### Task Not Created by Sequence
- Ensure the **task preset** exists
- Check if **"Assign this task to the property"** is toggled correctly
- Verify the trigger conditions are actually being met

## Drip Campaign Issues

### Drip Not Sending
- Check if **phone number is valid** on the record
- Verify **SMS integration** is active (smrtPhone, Twilio, or Plivo)
- Confirm **account timezone** is set in Settings → Profile
- Check if message is within **8 AM - 9 PM** window
- Verify the record hasn't been **removed** from the campaign

### Wrong Phone Number Receiving Messages
- Verify **"Send To"** selection in the drip step
- Check **which phone field** is populated on the record

### Drip Not Triggering from Sequence
- Verify the sequence is **toggled ON**
- Check if **conditions are met** (status, tags, lists)
- Review **Activity Log** on the property record for errors

### Drip Campaign Shows "Failed"
- Usually means **missing phone number or email** on the record
- Check the record's contact information
- Re-add to campaign after fixing the data

## Task Issues

### Task Not Appearing in Events
- Check if the task was **assigned to a user** or role
- Verify the **date filter** in Events isn't hiding future tasks
- Look in the **property record** → Assigned Events

### Task Assigned But User Can't See Record
- Restricted roles (Acquisitions, Dispositions, Researchers, Prospectors) can only see **records assigned to them**
- You must **assign the property record** to the user in addition to the task

### Task Preset Not Available in Sequence
- Ensure the preset is **saved** (not just created)
- Check if the preset **group** is visible
- Try refreshing the page

### Recurring Task Not Recurring
- Verify **recurrence settings** (daily, weekly, bi-weekly, monthly)
- Check if **"Skip Weekends"** is enabled (moves to Monday)
- Ensure the task is being **completed** (not just dismissed)

## Filter Preset Issues

### Preset Not Showing Expected Records
- Double-check each **filter block's settings** against the configuration
- Verify records have the correct **tags and list membership**
- Check if **Property Status** filter is excluding records you expect
- Ensure **Call Attempts** min/max are set correctly

### "No Results" in Preset
- Records may not have been **uploaded yet**
- Tags or lists may not match exactly (case-sensitive)
- The **"Do Not Include"** filter may be excluding everything

### Filter Blocks Conflicting
- Multiple filter blocks use **AND logic** (all must be true)
- Within "Any Lists (OR)" or "Any Tags (OR)", items use **OR logic**
- Check that blocks aren't contradicting each other

## SiftLine Board Issues

### Card Not Appearing on Board
- Check if the record has the **correct status** for that board
- Verify a sequence or manual action created the card
- Card may already exist on another board with the same name

### Can't Move Card Between Phases
- Verify you have **permission** to edit that board
- Check if the card is **locked** by another process

### Duplicate Cards on Same Board
- "Create New Card" action skips if card already exists
- Use **"Move Card"** or **"Duplicate Card"** action instead of "Create"
- Check if multiple sequences are creating cards for the same record

## General Issues

### Upload Not Triggering Sequences
- **Only Property Status Change** triggers work reliably with uploads
- Tag and List triggers are **manual-addition only**
- Set a default status during upload to trigger status-based sequences

### SMS Not Sending
- Verify **phone integration** (smrtPhone, Twilio, or Plivo)
- Check **A2P 10DLC compliance**
- Ensure the number is **not on DNC list**
- Confirm sending hours (8 AM - 9 PM in account timezone)

### Changes Not Saving
- Check your **internet connection**
- Verify you have the **correct permissions** for your role
- Try **refreshing the page** and re-applying changes

## Diagnostic Steps

When troubleshooting any issue:

1. **Check the Activity Log** — open the property record → Activity Log to see what actually happened
2. **Verify the sequence is ON** — sequences can be toggled off
3. **Test with one record** — manually trigger the condition on a single test record
4. **Check permissions** — verify your role has access to create/edit the component
5. **Review conditions** — ensure all conditions match the record's current state
6. **Check plan limits** — verify you haven't exceeded your sequence limit
