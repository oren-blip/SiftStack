# Filter Preset Configurations

This document provides the detailed filter block configurations for each standard preset in both Niche and Bulk Sequential marketing. Use these as a guide when constructing a user's custom preset plan.

## Niche Sequential Presets

### 00. Needs Skipped

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined first-to-market lists |
| `Any Tags (OR)` | General | Include user-defined data tag (e.g., `courthouse data`) |
| `Property Status` | Property Filters | **Do Not Include** → `Any Statuses` |
| `Call Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Numbers: No`, `Skiptraced: No` |

### 01. Skipped No Numbers

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined first-to-market lists |
| `Any Tags (OR)` | General | Include user-defined data tag (e.g., `courthouse data`) |
| `Params & Others` | General | `Numbers: No`, `Skiptraced: Yes` |

### 02. Ready to Call

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined first-to-market lists |
| `Any Tags (OR)` | General | Include user-defined data tag (e.g., `courthouse data`) |
| `Property Status` | Property Filters | **Do Not Include** → `Lead`, `Not Interested` (and other closed statuses) |
| `Call Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Numbers: Yes` |

### 03-05. FTM Follow Up 1, 2, 3

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined first-to-market lists |
| `Any Tags (OR)` | General | Include user-defined data tag (e.g., `courthouse data`) |
| `Call Attempts` | Marketing | `Min: X`, `Max: X` (where X is the attempt number) |
| `Phone Statuses` | General | **Do Not Include** → `Correct` |

### 06. Needs 1st Mail

| Filter Block | Category | Settings |
|---|---|---|
| `Call Attempts` | Marketing | `Min: 4` (or user-defined max attempts) |
| `Direct Mail Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Vacant Mailing: No` |
| `All Tags (AND)` | General | **Do Not Include** → `return mail` |

### 07. Mail Monthly

| Filter Block | Category | Settings |
|---|---|---|
| `Direct Mail Attempts`| Marketing | `Min: 1`, `Max: 12` (or user-defined max) |
| `Last Direct Mailed` | Marketing | `Prior to Date` → `1` `month` ago |
| `Params & Others` | General | `Vacant Mailing: No` |
| `All Tags (AND)` | General | **Do Not Include** → `return mail` |

### 08. Vacant Mailing → DP

| Filter Block | Category | Settings |
|---|---|---|
| `Params & Others` | General | `Vacant Mailing: Yes` |
| `Phone Statuses` | General | **Do Not Include at least one phone** → `Correct`, `Correct DNC` |

### 09. Return Mail → DP

| Filter Block | Category | Settings |
|---|---|---|
| `Any Tags (OR)` | General | `Include` → `return mail` |
| `Direct Mail Attempts`| Marketing | `Min: 1` |

### 10. No Response DM → DP

| Filter Block | Category | Settings |
|---|---|---|
| `Call Attempts` | Marketing | `Min: 4` (or user-defined max attempts) |
| `Direct Mail Attempts`| Marketing | `Min: 6`, `Max: 12` |
| `Phone Statuses` | General | **Do Not Include** → `Correct` |

### 11. Not Interested Qrtly

| Filter Block | Category | Settings |
|---|---|---|
| `Property Status` | Property Filters | `Include` → `Not Interested` |
| `Last Updated Field` | Property Filters | `Field: Status`, `Date: Prior to 3 months ago` |
| `Params & Others` | General | `Numbers: Yes` |

---

## Bulk Sequential Presets

### 00. Bulk Needs Skipped

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined bulk lists |
| `Property Status` | Property Filters | **Do Not Include** → `Any Statuses` |
| `Call Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Numbers: No`, `Skiptraced: No` |

### 01. Bulk Skipped NN

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined bulk lists |
| `Params & Others` | General | `Numbers: No`, `Skiptraced: Yes` |

### 02. Bulk Ready to Call

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined bulk lists |
| `Property Status` | Property Filters | **Do Not Include** → `Any Statuses` |
| `Call Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Numbers: Yes` |

### 03. Bulk Call Follow Up

| Filter Block | Category | Settings |
|---|---|---|
| `Any Lists (OR)` | General | Include user-defined bulk lists |
| `Property Status` | Property Filters | **Do Not Include** → `Any Statuses` |
| `Call Attempts` | Marketing | `Min: 1`, `Max: 6` (or user-defined range) |
| `Params & Others` | General | `Numbers: Yes` |

### 04. Bulk Needs 1st Mail

| Filter Block | Category | Settings |
|---|---|---|
| `Call Attempts` | Marketing | `Min: 7` (or user-defined max attempts + 1) |
| `Direct Mail Attempts` | Marketing | `Min: 0`, `Max: 0` |
| `Params & Others` | General | `Vacant Mailing: No` |

### 05. Bulk Mail Monthly

| Filter Block | Category | Settings |
|---|---|---|
| `Direct Mail Attempts`| Marketing | `Min: 1`, `Max: 12` |
| `Last Direct Mailed` | Marketing | `Prior to Date` → `1` `month` ago |
| `Params & Others` | General | `Vacant Mailing: No` |
| `All Tags (AND)` | General | **Do Not Include** → `return mail` |

### 06. Bulk Not Interested

| Filter Block | Category | Settings |
|---|---|---|
| `Property Status` | Property Filters | `Include` → `Not Interested` |
| `Last Updated Field` | Property Filters | `Field: Status`, `Date: Prior to 3 months ago` |

### 07. Exhausted CC → DP

| Filter Block | Category | Settings |
|---|---|---|
| `Property Status` | Property Filters | **Do Not Include** → `Any Statuses` |
| `Phone Statuses` | General | `Include` → `Wrong`, `Wrong DNC`, `Dead`, `DNC` |

### 08. Bulk Return Mail → DP

| Filter Block | Category | Settings |
|---|---|---|
| `Any Tags (OR)` | General | `Include` → `return mail` |
| `Direct Mail Attempts`| Marketing | `Min: 1` |
| `Phone Statuses` | General | **Do Not Include at least one phone** → `Correct`, `Correct DNC` |
